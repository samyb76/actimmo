import streamlit as st
import pandas as pd
import psycopg2
import base64
import os


# Chargement du favicon depuis le logo
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

st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@600;700&family=DM+Sans:wght@300;400;500&display=swap');
    html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
    .block-container { padding: 2rem 2.5rem; }

    .header-bar {
        background: transparent;
        padding: 0.5rem 2rem; border-radius: 0; margin-bottom: 1.8rem;
        display: flex; align-items: center; justify-content: center;
    }
    .header-bar img {
        max-height: 200px;
        max-width: 100%;
        object-fit: contain;
    }

    .kpi-card {
        background: white; border-radius: 12px; padding: 1.2rem 1.5rem;
        border-left: 5px solid #d4145a;
        box-shadow: 0 2px 10px rgba(0,0,0,0.06);
        margin-bottom: 1rem;
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
""",
    unsafe_allow_html=True,
)

# ── Session state ──────────────────────────────────────────────────────────────
for k, v in [
    ("confirm_delete", None),
    ("confirm_delete_sect", None),
]:
    if k not in st.session_state:
        st.session_state[k] = v


# ── Connexion BDD Neon via secrets ─────────────────────────────────────────────
def get_conn():
    return psycopg2.connect(
        host=st.secrets["db"]["host"],
        port=st.secrets["db"]["port"],
        dbname=st.secrets["db"]["dbname"],
        user=st.secrets["db"]["user"],
        password=st.secrets["db"]["password"],
        sslmode=st.secrets["db"].get("sslmode", "require"),
        connect_timeout=10,
    )


@st.cache_data(ttl=30)
def load_biens():
    conn = get_conn()
    try:
        df = pd.read_sql(
            """
            SELECT
                b.id,
                b.budget,
                b.nombre_chambres,
                b.nombre_chambres_max,
                b.acquereur_prenom,
                b.acquereur_nom,
                b.acquereur_tel,
                b.acquereur_mail,
                b.created_at,
                COALESCE(
                    STRING_AGG(s.nom, ', ' ORDER BY s.nom), '—'
                ) AS secteurs
            FROM biens b
            LEFT JOIN acquereur_secteurs acs ON acs.acquereur_id = b.id
            LEFT JOIN secteurs s ON s.id = acs.secteur_id
            GROUP BY
                b.id,
                b.budget,
                b.nombre_chambres,
                b.nombre_chambres_max,
                b.acquereur_prenom,
                b.acquereur_nom,
                b.acquereur_tel,
                b.acquereur_mail,
                b.created_at
            ORDER BY b.id
            """,
            conn,
        )
        return df
    finally:
        conn.close()


@st.cache_data(ttl=30)
def load_secteurs():
    conn = get_conn()
    try:
        df = pd.read_sql("SELECT id, nom FROM secteurs ORDER BY nom", conn)
        return df
    finally:
        conn.close()


def refresh():
    load_biens.clear()
    load_secteurs.clear()
    st.rerun()


# ── Header avec logo ───────────────────────────────────────────────────────────
LOGO_EXTENSIONS = ["logo.png", "logo.jpg", "logo.jpeg", "logo.svg"]
logo_path = None
for ext in LOGO_EXTENSIONS:
    if os.path.isfile(ext):
        logo_path = ext
        break

if logo_path:
    with open(logo_path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    mime = (
        "image/png"
        if logo_path.endswith(".png")
        else "image/jpeg" if logo_path.endswith((".jpg", ".jpeg")) else "image/svg+xml"
    )
    logo_src = f"data:{mime};base64,{data}"
    header_content = f'<img src="{logo_src}" alt="Act\'Immobilier" style="max-height:200px;max-width:100%;object-fit:contain;" />'
else:
    header_content = "<span style=\"font-family:'Playfair Display',serif;font-size:1.9rem;color:#8dc63f;\">🏛 Act'Immobilier</span>"

st.markdown(
    f"""
<div class="header-bar">
    {header_content}
</div>
""",
    unsafe_allow_html=True,
)

# ── Chargement ─────────────────────────────────────────────────────────────────
try:
    df = load_biens()
    secteurs_df = load_secteurs()
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
    ch_vals = sorted(df["nombre_chambres"].dropna().astype(int).unique().tolist())
    if len(ch_vals) >= 2:
        ch_range = st.slider(
            "Nombre de chambres",
            min_value=ch_vals[0],
            max_value=ch_vals[-1],
            value=(ch_vals[0], ch_vals[-1]),
            step=1,
        )
    elif len(ch_vals) == 1:
        ch_range = (ch_vals[0], ch_vals[0])
        st.info(f"Chambres : {ch_vals[0]}")
    else:
        ch_range = (1, 10)

with f3:
    budget_valides = df["budget"].dropna()
    pmin = int(budget_valides.min()) if len(budget_valides) > 0 else 0
    pmax = int(budget_valides.max()) if len(budget_valides) > 0 else 100000
    if pmin == pmax:
        pmax += 1
    budget_range = st.slider(
        "Fourchette de budget (€)", pmin, pmax, (pmin, pmax), step=500
    )

with f4:
    tri_col = st.selectbox("Trier par", ["budget", "nombre_chambres", "secteurs"])

with f5:
    tri_ordre = st.radio("Ordre", ["Croissant", "Décroissant"], horizontal=True)


# ── Filtrage ───────────────────────────────────────────────────────────────────
def chevauche(r):
    ch_min = r["nombre_chambres"] if pd.notna(r["nombre_chambres"]) else None
    ch_max = r["nombre_chambres_max"] if pd.notna(r["nombre_chambres_max"]) else ch_min
    if ch_min is None:
        return False
    return ch_min <= ch_range[1] and ch_max >= ch_range[0]


dff = df.copy()
if not dff.empty and sel_secteur != "Tous":
    dff = dff[dff["secteurs"].str.contains(sel_secteur, na=False)]
if not dff.empty:
    dff = dff[dff.apply(chevauche, axis=1)]
if not dff.empty:
    dff = dff[(dff["budget"] >= budget_range[0]) & (dff["budget"] <= budget_range[1])]
dff = (
    dff.sort_values(tri_col, ascending=(tri_ordre == "Croissant"))
    if not dff.empty
    else dff
)

# ── KPI ────────────────────────────────────────────────────────────────────────
st.markdown(
    f"""<div class="kpi-card">
    <div class="val">{len(dff)}</div>
    <div class="lbl">Acquéreurs affichés</div>
</div>""",
    unsafe_allow_html=True,
)

# ── Tableau ────────────────────────────────────────────────────────────────────
st.markdown(
    '<div class="section-title">📋 Liste des acquéreurs</div>', unsafe_allow_html=True
)

disp = dff[
    [
        "secteurs",
        "budget",
        "nombre_chambres",
        "nombre_chambres_max",
        "acquereur_prenom",
        "acquereur_nom",
        "acquereur_tel",
        "acquereur_mail",
    ]
].copy()

disp["budget"] = disp["budget"].apply(lambda x: f"{x:,.0f} €")
disp["acquereur_prenom"] = disp["acquereur_prenom"].fillna("—")
disp["acquereur_nom"] = disp["acquereur_nom"].fillna("—")
disp["acquereur_tel"] = disp["acquereur_tel"].fillna("—")
disp["acquereur_mail"] = disp["acquereur_mail"].fillna("—")


def fmt_chambres(r):
    try:
        ch_min = int(r["nombre_chambres"]) if pd.notna(r["nombre_chambres"]) else None
        ch_max = (
            int(r["nombre_chambres_max"])
            if pd.notna(r["nombre_chambres_max"])
            else None
        )
        if ch_min is None:
            return "—"
        if ch_max and ch_max != ch_min:
            return f"{ch_min} à {ch_max}"
        return str(ch_min)
    except Exception:
        return "—"


disp["nombre_chambres"] = disp.apply(fmt_chambres, axis=1)
disp.drop(columns=["nombre_chambres_max"], inplace=True)
disp.rename(
    columns={
        "secteurs": "Secteur(s)",
        "nombre_chambres": "Chambres",
        "budget": "Budget",
        "acquereur_prenom": "Prénom",
        "acquereur_nom": "Nom",
        "acquereur_tel": "Téléphone",
        "acquereur_mail": "Mail",
    },
    inplace=True,
)

st.dataframe(
    disp,
    use_container_width=True,
    hide_index=True,
    height=420,
    column_config={
        "Secteur(s)": st.column_config.TextColumn(width="medium"),
        "Budget": st.column_config.TextColumn(width="small"),
        "Chambres": st.column_config.TextColumn(width="small"),
        "Prénom": st.column_config.TextColumn(width="small"),
        "Nom": st.column_config.TextColumn(width="small"),
        "Téléphone": st.column_config.TextColumn(width="medium"),
        "Mail": st.column_config.TextColumn(width="medium"),
    },
)
st.caption(f"{len(dff)} acquéreur(s) affiché(s) sur {len(df)} au total")

# ── CRUD ───────────────────────────────────────────────────────────────────────
st.markdown(
    '<div class="section-title">✏️ Gestion des données</div>', unsafe_allow_html=True
)

tab1, tab2, tab3 = st.tabs(
    [
        "➕ Ajouter un acquéreur",
        "🗑️ Supprimer un acquéreur",
        "🏙️ Gérer les secteurs",
    ]
)

# ── Ajouter ───────────────────────────────────────────────────────────────────
with tab1:
    with st.form("add_acquereur", clear_on_submit=True):
        sect_map = dict(zip(secteurs_df["nom"], secteurs_df["id"]))

        c1, c2, c3 = st.columns(3)
        with c1:
            budget_new = st.number_input(
                "Budget (€) *", min_value=0, step=500, value=None
            )
        with c2:
            nb_ch_new = st.number_input(
                "Chambres min *", min_value=1, max_value=20, step=1, value=None
            )
        with c3:
            nb_ch_max_new = st.number_input(
                "Chambres max",
                min_value=1,
                max_value=20,
                step=1,
                value=None,
                help="Laisser vide si pas de maximum",
            )

        sects_choisis = st.multiselect(
            "Secteur(s) *",
            options=list(sect_map.keys()),
            placeholder="Choisir un ou plusieurs secteurs",
        )

        c3, c4 = st.columns(2)
        with c3:
            acq_prenom = st.text_input("Prénom acquéreur")
        with c4:
            acq_nom = st.text_input("Nom acquéreur")

        c5, c6 = st.columns(2)
        with c5:
            acq_tel = st.text_input("Téléphone acquéreur")
        with c6:
            acq_mail = st.text_input("Mail acquéreur")

        if st.form_submit_button("✅ Ajouter l'acquéreur", use_container_width=True):
            if not sects_choisis:
                st.error("Veuillez choisir au moins un secteur.")
            elif not budget_new:
                st.error("Le budget est obligatoire.")
            elif not nb_ch_new:
                st.error("Le nombre de chambres minimum est obligatoire.")
            elif nb_ch_max_new and nb_ch_max_new < nb_ch_new:
                st.error("Le maximum doit être supérieur ou égal au minimum.")
            else:
                conn = None
                cur = None
                try:
                    conn = get_conn()
                    cur = conn.cursor()
                    cur.execute(
                        """INSERT INTO biens
                           (budget, nombre_chambres, nombre_chambres_max,
                            acquereur_prenom, acquereur_nom,
                            acquereur_tel, acquereur_mail)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)
                           RETURNING id""",
                        (
                            budget_new,
                            nb_ch_new,
                            nb_ch_max_new or None,
                            acq_prenom.strip() or None,
                            acq_nom.strip() or None,
                            acq_tel.strip() or None,
                            acq_mail.strip() or None,
                        ),
                    )
                    new_id = cur.fetchone()[0]

                    for sect_nom in sects_choisis:
                        cur.execute(
                            "INSERT INTO acquereur_secteurs (acquereur_id, secteur_id) VALUES (%s, %s)",
                            (new_id, sect_map[sect_nom]),
                        )

                    conn.commit()
                    st.success("✅ Acquéreur ajouté !")
                    refresh()

                except Exception as e:
                    if conn:
                        conn.rollback()
                    st.error(f"Erreur : {e}")

                finally:
                    if cur:
                        cur.close()
                    if conn:
                        conn.close()

# ── Supprimer ─────────────────────────────────────────────────────────────────
with tab2:
    if len(df) > 0:
        opts = {
            (
                lambda r: (
                    lambda ch_min, ch_max: (
                        f"{r['acquereur_prenom'] or ''} {r['acquereur_nom'] or ''} — {r['secteurs']} | {int(r['budget']):,} € | "
                        f"{ch_min} à {ch_max} ch."
                        if ch_max and ch_max != ch_min
                        else f"{r['acquereur_prenom'] or ''} {r['acquereur_nom'] or ''} — {r['secteurs']} | {int(r['budget']):,} € | {ch_min} ch."
                    )
                )(
                    int(r["nombre_chambres"]) if pd.notna(r["nombre_chambres"]) else 0,
                    (
                        int(r["nombre_chambres_max"])
                        if pd.notna(r["nombre_chambres_max"])
                        else None
                    ),
                )
            )(r).strip(): r["id"]
            for _, r in df.iterrows()
        }

        sel = st.selectbox(
            "Acquéreur à supprimer", ["Choisir un acquéreur"] + list(opts.keys())
        )
        if sel == "Choisir un acquéreur":
            acq_id = None
        else:
            acq_id = opts[sel]

        if st.button("🗑️ Supprimer", type="primary"):
            if sel == "Choisir un acquéreur":
                st.error("Veuillez choisir un acquéreur.")
            else:
                st.session_state["confirm_delete"] = acq_id

        if acq_id and st.session_state.get("confirm_delete") == acq_id:
            st.warning(f"⚠️ Confirmer la suppression de : **{sel}** ?")
            cy, cn = st.columns(2)
            with cy:
                if st.button("✅ Oui, supprimer", use_container_width=True):
                    conn = None
                    cur = None
                    try:
                        conn = get_conn()
                        cur = conn.cursor()
                        cur.execute("DELETE FROM biens WHERE id = %s", (acq_id,))
                        conn.commit()
                        st.session_state["confirm_delete"] = None
                        st.success("✅ Acquéreur supprimé !")
                        refresh()
                    except Exception as e:
                        if conn:
                            conn.rollback()
                        st.error(f"Erreur : {e}")
                    finally:
                        if cur:
                            cur.close()
                        if conn:
                            conn.close()
            with cn:
                if st.button("❌ Annuler", use_container_width=True):
                    st.session_state["confirm_delete"] = None
    else:
        st.info("Aucun acquéreur en base.")

# ── Gérer les secteurs ─────────────────────────────────────────────────────────
with tab3:
    st.markdown("**Secteurs existants**")
    st.dataframe(
        secteurs_df[["nom"]].rename(columns={"nom": "Nom"}),
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("**Ajouter un secteur**")
    with st.form("add_secteur", clear_on_submit=True):
        nom_new = st.text_input("Nom *", placeholder="Ex : Centre-ville…")
        if st.form_submit_button("✅ Ajouter", use_container_width=True):
            if not nom_new.strip():
                st.error("Le nom est obligatoire.")
            else:
                conn = None
                cur = None
                try:
                    conn = get_conn()
                    cur = conn.cursor()
                    cur.execute(
                        "INSERT INTO secteurs (nom) VALUES (%s)", (nom_new.strip(),)
                    )
                    conn.commit()
                    st.success(f"✅ Secteur « {nom_new} » ajouté !")
                    refresh()
                except Exception as e:
                    if conn:
                        conn.rollback()
                    st.error(f"Erreur : {e}")
                finally:
                    if cur:
                        cur.close()
                    if conn:
                        conn.close()

    st.markdown("**Supprimer un secteur**")
    if len(secteurs_df) > 0:
        sect_del_map = dict(zip(secteurs_df["nom"], secteurs_df["id"]))
        sect_del_name = st.selectbox(
            "Secteur à supprimer",
            ["Choisir un secteur"] + list(sect_del_map.keys()),
            key="sect_del",
        )

        if st.button("🗑️ Supprimer le secteur", type="primary"):
            if sect_del_name == "Choisir un secteur":
                st.error("Veuillez choisir un secteur.")
            else:
                st.session_state["confirm_delete_sect"] = sect_del_name

        if (
            st.session_state.get("confirm_delete_sect") == sect_del_name
            and sect_del_name != "Choisir un secteur"
        ):
            conn = None
            cur = None
            try:
                conn = get_conn()
                cur = conn.cursor()
                cur.execute(
                    "SELECT COUNT(*) FROM acquereur_secteurs WHERE secteur_id = %s",
                    (sect_del_map[sect_del_name],),
                )
                acq_lies = cur.fetchone()[0]
            except Exception as e:
                acq_lies = None
                st.error(f"Erreur : {e}")
            finally:
                if cur:
                    cur.close()
                if conn:
                    conn.close()

            if acq_lies is not None and acq_lies > 0:
                st.error(
                    f"❌ Impossible de supprimer « {sect_del_name} » : "
                    f"{acq_lies} acquéreur(s) y sont rattachés."
                )
                st.session_state["confirm_delete_sect"] = None
            elif acq_lies == 0:
                st.warning(
                    f"⚠️ Confirmer la suppression du secteur **{sect_del_name}** ?"
                )
                cy, cn = st.columns(2)
                with cy:
                    if st.button(
                        "✅ Oui, supprimer", key="yes_sect", use_container_width=True
                    ):
                        conn = None
                        cur = None
                        try:
                            conn = get_conn()
                            cur = conn.cursor()
                            cur.execute(
                                "DELETE FROM secteurs WHERE id = %s",
                                (sect_del_map[sect_del_name],),
                            )
                            conn.commit()
                            st.session_state["confirm_delete_sect"] = None
                            st.success(f"✅ Secteur « {sect_del_name} » supprimé !")
                            refresh()
                        except Exception as e:
                            if conn:
                                conn.rollback()
                            st.error(f"Erreur : {e}")
                        finally:
                            if cur:
                                cur.close()
                            if conn:
                                conn.close()
                with cn:
                    if st.button("❌ Annuler", key="no_sect", use_container_width=True):
                        st.session_state["confirm_delete_sect"] = None
    else:
        st.info("Aucun secteur en base.")
