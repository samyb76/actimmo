import streamlit as st
import pandas as pd
import psycopg2
from psycopg2 import pool
import base64
import os


# ── Favicon ────────────────────────────────────────────────────────────────────
def get_favicon():
    for name in ["logo.png", "logo.jpg", "logo.jpeg"]:
        if os.path.isfile(name):
            from PIL import Image
            return Image.open(name)
    return "🏠"


st.set_page_config(
    page_title="Act'Immobilier",
    page_icon=get_favicon(),
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=DM+Sans:wght@300;400;500&display=swap');
    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
    .block-container { padding: 2rem 2.5rem; }

    .header-bar {
        background: transparent;
        padding: 0.5rem 2rem; border-radius: 0; margin-bottom: 1.8rem;
        display: flex; align-items: center; justify-content: center;
    }
    .header-bar img { max-height: 200px; max-width: 100%; object-fit: contain; }

    .kpi-card {
        background: white; border-radius: 12px; padding: 1.2rem 1.5rem;
        border-left: 5px solid #d4145a;
        box-shadow: 0 2px 10px rgba(0,0,0,0.06); margin-bottom: 1rem;
    }
    .kpi-card .val { font-family: 'Playfair Display', serif; font-size: 2.2rem; color: #1a1a1a; }
    .kpi-card .lbl { font-size: 0.75rem; color: #999; text-transform: uppercase; letter-spacing: 0.06em; }

    .section-title {
        font-family: 'Playfair Display', serif; font-size: 1.2rem;
        color: #d4145a; border-bottom: 2px solid #8dc63f;
        background: #fdf9ff; padding: 0.5rem 0.8rem;
        border-radius: 6px 6px 0 0; margin: 1.5rem 0 1rem;
    }

    div[data-testid="stSidebar"] { display: none; }
    div[data-testid="collapsedControl"] { display: none; }
    .stButton > button { border-radius: 8px; font-weight: 500; }
</style>
""", unsafe_allow_html=True)

# ── Session state ──────────────────────────────────────────────────────────────
for k, v in [("confirm_delete", None), ("confirm_delete_sect", None)]:
    if k not in st.session_state:
        st.session_state[k] = v

# ── Pool de connexions (1 seule instance partagée) ─────────────────────────────
# st.cache_resource = jamais recréé entre les reruns → minimise les réveils Neon
@st.cache_resource
def get_pool():
    return pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=3,
        dsn=st.secrets["db"]["dsn"],  # Connection string complète dans secrets.toml
        connect_timeout=10,
    )

def get_conn():
    try:
        return get_pool().getconn()
    except Exception:
        return psycopg2.connect(st.secrets["db"]["dsn"], connect_timeout=10)

def release_conn(conn):
    try:
        get_pool().putconn(conn)
    except Exception:
        try: conn.close()
        except Exception: pass

# ── Chargement données — TTL long pour limiter les requêtes BDD ────────────────
# 1 seule requête SQL au lieu de 2 → moitié moins de réveils Neon
@st.cache_data(ttl=600)  # Cache 10 minutes
def load_all():
    conn = get_conn()
    try:
        biens = pd.read_sql("""
            SELECT
                b.id, b.budget, b.nombre_chambres, b.nombre_chambres_max,
                b.acquereur_prenom, b.acquereur_nom,
                b.acquereur_tel, b.acquereur_mail, b.created_at,
                COALESCE(STRING_AGG(s.nom, ', ' ORDER BY s.nom), '—') AS secteurs
            FROM biens b
            LEFT JOIN acquereur_secteurs acs ON acs.acquereur_id = b.id
            LEFT JOIN secteurs s ON s.id = acs.secteur_id
            GROUP BY b.id, b.budget, b.nombre_chambres, b.nombre_chambres_max,
                     b.acquereur_prenom, b.acquereur_nom,
                     b.acquereur_tel, b.acquereur_mail, b.created_at
            ORDER BY b.id
        """, conn)
        secteurs = pd.read_sql("SELECT id, nom FROM secteurs ORDER BY nom", conn)
        return biens, secteurs
    finally:
        release_conn(conn)

def refresh():
    load_all.clear()
    st.rerun()

# ── Logo ───────────────────────────────────────────────────────────────────────
for ext in ["logo.png", "logo.jpg", "logo.jpeg", "logo.svg"]:
    if os.path.isfile(ext):
        with open(ext, "rb") as f:
            data = base64.b64encode(f.read()).decode()
        mime = "image/png" if ext.endswith(".png") else \
               "image/jpeg" if ext.endswith((".jpg", ".jpeg")) else "image/svg+xml"
        header_content = f'<img src="data:{mime};base64,{data}" alt="Act\'Immobilier" style="max-height:200px;max-width:100%;object-fit:contain;" />'
        break
else:
    header_content = "<span style=\"font-family:'Playfair Display',serif;font-size:1.9rem;color:#8dc63f;\">🏛 Act'Immobilier</span>"

st.markdown(f'<div class="header-bar">{header_content}</div>', unsafe_allow_html=True)

# ── Chargement ─────────────────────────────────────────────────────────────────
try:
    df, secteurs_df = load_all()
except Exception as e:
    st.error(f"❌ Connexion impossible : {e}")
    st.stop()

# ── Filtres ────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">🔍 Filtres</div>', unsafe_allow_html=True)

f1, f2, f3, f4, f5 = st.columns([2, 2, 2, 2, 2])

with f1:
    sect_opts = ["Tous"] + sorted(secteurs_df["nom"].tolist())
    sel_secteur = st.selectbox("Secteur", sect_opts)

with f2:
    ch_min_vals = pd.to_numeric(df["nombre_chambres"], errors="coerce").dropna()
    ch_max_vals = pd.to_numeric(df["nombre_chambres_max"], errors="coerce").dropna()
    if len(ch_min_vals) > 0:
        sl_min = int(ch_min_vals.min())
        sl_max = int(max(ch_min_vals.max(), ch_max_vals.max() if len(ch_max_vals) > 0 else ch_min_vals.max()))
        if sl_min == sl_max: sl_max += 1
        ch_range = st.slider("Nombre de chambres", sl_min, sl_max, (sl_min, sl_max), step=1)
    else:
        ch_range = (1, 10)

with f3:
    budget_vals = pd.to_numeric(df["budget"], errors="coerce").dropna()
    pmin = int(budget_vals.min()) if len(budget_vals) > 0 else 0
    pmax = int(budget_vals.max()) if len(budget_vals) > 0 else 100000
    if pmin == pmax: pmax += 1
    budget_range = st.slider("Fourchette de budget (€)", pmin, pmax, (pmin, pmax), step=500)

with f4:
    tri_col = st.selectbox("Trier par", ["budget", "nombre_chambres", "secteurs"])

with f5:
    tri_ordre = st.radio("Ordre", ["Croissant", "Décroissant"], horizontal=True)

# ── Filtrage ───────────────────────────────────────────────────────────────────
def filtre_chambres(r):
    ch_min = pd.to_numeric(r["nombre_chambres"], errors="coerce")
    ch_max = pd.to_numeric(r["nombre_chambres_max"], errors="coerce")
    if pd.isna(ch_min): return False
    if pd.isna(ch_max): ch_max = ch_min
    return not (ch_max < ch_range[0] or ch_min > ch_range[1])

dff = df.copy()
if not dff.empty and sel_secteur != "Tous":
    dff = dff[dff["secteurs"].str.contains(sel_secteur, na=False)]
if not dff.empty:
    dff = dff[dff.apply(filtre_chambres, axis=1)]
if not dff.empty:
    budget_num = pd.to_numeric(dff["budget"], errors="coerce")
    dff = dff[(budget_num >= budget_range[0]) & (budget_num <= budget_range[1])]
if not dff.empty:
    dff = dff.sort_values(tri_col, ascending=(tri_ordre == "Croissant"))

# ── KPI ────────────────────────────────────────────────────────────────────────
st.markdown(f"""<div class="kpi-card">
    <div class="val">{len(dff)}</div>
    <div class="lbl">Acquéreurs affichés</div>
</div>""", unsafe_allow_html=True)

# ── Tableau ────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">📋 Liste des acquéreurs</div>', unsafe_allow_html=True)

def fmt_chambres(r):
    try:
        ch_min = pd.to_numeric(r["nombre_chambres"], errors="coerce")
        ch_max = pd.to_numeric(r["nombre_chambres_max"], errors="coerce")
        if pd.isna(ch_min): return "—"
        if pd.notna(ch_max) and ch_max != ch_min: return f"{int(ch_min)} à {int(ch_max)}"
        return str(int(ch_min))
    except Exception: return "—"

disp = dff[["secteurs","budget","nombre_chambres","nombre_chambres_max",
            "acquereur_prenom","acquereur_nom","acquereur_tel","acquereur_mail"]].copy()
disp["budget"]           = pd.to_numeric(disp["budget"], errors="coerce").apply(lambda x: f"{x:,.0f} €" if pd.notna(x) else "—")
disp["nombre_chambres"]  = disp.apply(fmt_chambres, axis=1)
disp["acquereur_prenom"] = disp["acquereur_prenom"].fillna("—")
disp["acquereur_nom"]    = disp["acquereur_nom"].fillna("—")
disp["acquereur_tel"]    = disp["acquereur_tel"].fillna("—")
disp["acquereur_mail"]   = disp["acquereur_mail"].fillna("—")
disp.drop(columns=["nombre_chambres_max"], inplace=True)
disp.rename(columns={
    "secteurs": "Secteur(s)", "nombre_chambres": "Chambres", "budget": "Budget",
    "acquereur_prenom": "Prénom", "acquereur_nom": "Nom",
    "acquereur_tel": "Téléphone", "acquereur_mail": "Mail",
}, inplace=True)

st.dataframe(disp, use_container_width=True, hide_index=True, height=420,
    column_config={
        "Secteur(s)": st.column_config.TextColumn(width="medium"),
        "Budget":     st.column_config.TextColumn(width="small"),
        "Chambres":   st.column_config.TextColumn(width="small"),
        "Prénom":     st.column_config.TextColumn(width="small"),
        "Nom":        st.column_config.TextColumn(width="small"),
        "Téléphone":  st.column_config.TextColumn(width="medium"),
        "Mail":       st.column_config.TextColumn(width="medium"),
    })
st.caption(f"{len(dff)} acquéreur(s) affiché(s) sur {len(df)} au total")

# ── CRUD ───────────────────────────────────────────────────────────────────────
st.markdown('<div class="section-title">✏️ Gestion des données</div>', unsafe_allow_html=True)

tab1, tab2, tab3 = st.tabs(["➕ Ajouter un acquéreur", "🗑️ Supprimer un acquéreur", "🏙️ Gérer les secteurs"])

# ── Ajouter ───────────────────────────────────────────────────────────────────
with tab1:
    with st.form("add_acquereur", clear_on_submit=True):
        sect_map = dict(zip(secteurs_df["nom"], secteurs_df["id"]))
        c1, c2, c3 = st.columns(3)
        with c1: budget_new  = st.number_input("Budget (€) *", min_value=0, step=500, value=None)
        with c2: nb_ch_new   = st.number_input("Chambres min *", min_value=1, max_value=20, step=1, value=None)
        with c3: nb_ch_max_new = st.number_input("Chambres max", min_value=1, max_value=20, step=1, value=None, help="Laisser vide si pas de maximum")

        sects_choisis = st.multiselect("Secteur(s) *", options=list(sect_map.keys()), placeholder="Choisir un ou plusieurs secteurs")

        c4, c5 = st.columns(2)
        with c4: acq_prenom = st.text_input("Prénom acquéreur")
        with c5: acq_nom    = st.text_input("Nom acquéreur")
        c6, c7 = st.columns(2)
        with c6: acq_tel  = st.text_input("Téléphone acquéreur")
        with c7: acq_mail = st.text_input("Mail acquéreur")

        if st.form_submit_button("✅ Ajouter l'acquéreur", use_container_width=True):
            if not sects_choisis:               st.error("Veuillez choisir au moins un secteur.")
            elif not budget_new:                st.error("Le budget est obligatoire.")
            elif not nb_ch_new:                 st.error("Le nombre de chambres minimum est obligatoire.")
            elif nb_ch_max_new and nb_ch_max_new < nb_ch_new: st.error("Le maximum doit être supérieur ou égal au minimum.")
            else:
                conn = get_conn()
                try:
                    cur = conn.cursor()
                    cur.execute("""INSERT INTO biens
                        (budget, nombre_chambres, nombre_chambres_max,
                         acquereur_prenom, acquereur_nom, acquereur_tel, acquereur_mail)
                        VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (budget_new, nb_ch_new, nb_ch_max_new or None,
                         acq_prenom.strip() or None, acq_nom.strip() or None,
                         acq_tel.strip() or None, acq_mail.strip() or None))
                    new_id = cur.fetchone()[0]
                    for s in sects_choisis:
                        cur.execute("INSERT INTO acquereur_secteurs (acquereur_id, secteur_id) VALUES (%s,%s)",
                                    (new_id, sect_map[s]))
                    conn.commit(); cur.close()
                    st.success("✅ Acquéreur ajouté !")
                    refresh()
                except Exception as e:
                    conn.rollback(); st.error(f"Erreur : {e}")
                finally:
                    release_conn(conn)

# ── Supprimer acquéreur ────────────────────────────────────────────────────────
with tab2:
    if len(df) > 0:
        opts = {}
        for _, r in df.iterrows():
            ch_min = pd.to_numeric(r["nombre_chambres"], errors="coerce")
            ch_max = pd.to_numeric(r["nombre_chambres_max"], errors="coerce")
            ch_txt = f"{int(ch_min)} à {int(ch_max)} ch." if pd.notna(ch_max) and ch_max != ch_min else (f"{int(ch_min)} ch." if pd.notna(ch_min) else "—")
            label  = f"{r['acquereur_prenom'] or ''} {r['acquereur_nom'] or ''} — {r['secteurs']} | {int(r['budget']):,} € | {ch_txt}".strip()
            opts[label] = r["id"]

        sel    = st.selectbox("Acquéreur à supprimer", ["Choisir un acquéreur"] + list(opts.keys()))
        acq_id = None if sel == "Choisir un acquéreur" else opts[sel]

        if st.button("🗑️ Supprimer", type="primary"):
            if not acq_id: st.error("Veuillez choisir un acquéreur.")
            else: st.session_state["confirm_delete"] = acq_id

        if acq_id and st.session_state.get("confirm_delete") == acq_id:
            st.warning(f"⚠️ Confirmer la suppression de : **{sel}** ?")
            cy, cn = st.columns(2)
            with cy:
                if st.button("✅ Oui, supprimer", use_container_width=True):
                    conn = get_conn()
                    try:
                        cur = conn.cursor()
                        cur.execute("DELETE FROM biens WHERE id = %s", (acq_id,))
                        conn.commit(); cur.close()
                        st.session_state["confirm_delete"] = None
                        st.success("✅ Acquéreur supprimé !")
                        refresh()
                    except Exception as e:
                        conn.rollback(); st.error(f"Erreur : {e}")
                    finally:
                        release_conn(conn)
            with cn:
                if st.button("❌ Annuler", use_container_width=True):
                    st.session_state["confirm_delete"] = None
    else:
        st.info("Aucun acquéreur en base.")

# ── Gérer les secteurs ─────────────────────────────────────────────────────────
with tab3:
    st.markdown("**Secteurs existants**")
    st.dataframe(secteurs_df[["nom"]].rename(columns={"nom": "Nom"}),
                 use_container_width=True, hide_index=True)

    st.markdown("**Ajouter un secteur**")
    with st.form("add_secteur", clear_on_submit=True):
        nom_new = st.text_input("Nom *", placeholder="Ex : Centre-ville…")
        if st.form_submit_button("✅ Ajouter", use_container_width=True):
            if not nom_new.strip(): st.error("Le nom est obligatoire.")
            else:
                conn = get_conn()
                try:
                    cur = conn.cursor()
                    cur.execute("INSERT INTO secteurs (nom) VALUES (%s)", (nom_new.strip(),))
                    conn.commit(); cur.close()
                    st.success(f"✅ Secteur « {nom_new} » ajouté !")
                    refresh()
                except Exception as e:
                    conn.rollback(); st.error(f"Erreur : {e}")
                finally:
                    release_conn(conn)

    st.markdown("**Supprimer un secteur**")
    if len(secteurs_df) > 0:
        sect_del_map  = dict(zip(secteurs_df["nom"], secteurs_df["id"]))
        sect_del_name = st.selectbox("Secteur à supprimer",
                                     ["Choisir un secteur"] + list(sect_del_map.keys()), key="sect_del")

        if st.button("🗑️ Supprimer le secteur", type="primary"):
            if sect_del_name == "Choisir un secteur": st.error("Veuillez choisir un secteur.")
            else: st.session_state["confirm_delete_sect"] = sect_del_name

        if st.session_state.get("confirm_delete_sect") == sect_del_name and sect_del_name != "Choisir un secteur":
            conn = get_conn()
            try:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM acquereur_secteurs WHERE secteur_id = %s",
                            (sect_del_map[sect_del_name],))
                acq_lies = cur.fetchone()[0]; cur.close()
            except Exception as e:
                acq_lies = None; st.error(f"Erreur : {e}")
            finally:
                release_conn(conn)

            if acq_lies and acq_lies > 0:
                st.error(f"❌ Impossible : {acq_lies} acquéreur(s) rattachés à « {sect_del_name} ».")
                st.session_state["confirm_delete_sect"] = None
            elif acq_lies == 0:
                st.warning(f"⚠️ Confirmer la suppression du secteur **{sect_del_name}** ?")
                cy, cn = st.columns(2)
                with cy:
                    if st.button("✅ Oui, supprimer", key="yes_sect", use_container_width=True):
                        conn = get_conn()
                        try:
                            cur = conn.cursor()
                            cur.execute("DELETE FROM secteurs WHERE id = %s", (sect_del_map[sect_del_name],))
                            conn.commit(); cur.close()
                            st.session_state["confirm_delete_sect"] = None
                            st.success(f"✅ Secteur « {sect_del_name} » supprimé !")
                            refresh()
                        except Exception as e:
                            conn.rollback(); st.error(f"Erreur : {e}")
                        finally:
                            release_conn(conn)
                with cn:
                    if st.button("❌ Annuler", key="no_sect", use_container_width=True):
                        st.session_state["confirm_delete_sect"] = None
    else:
        st.info("Aucun secteur en base.")