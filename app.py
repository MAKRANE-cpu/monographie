import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai

# --- 1. CONFIGURATION ET STYLE ---
st.set_page_config(
    page_title="Agri-Dashboard Chefchaouen",
    page_icon="🌿",
    layout="wide"
)

# Style CSS personnalisé pour un look "Entreprise"
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { 
        background-color: #ffffff; 
        padding: 20px; 
        border-radius: 12px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.05);
        border: 1px solid #eef0f2;
    }
    div[data-testid="stSidebar"] { background-color: #1e293b; color: white; }
    .stButton>button { border-radius: 8px; width: 100%; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. FONCTIONS DE CHARGEMENT ---
@st.cache_data(ttl=600)
def load_all_data(sheet_id):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    sh = client.open_by_key(sheet_id)
    
    all_sheets = {}
    for ws in sh.worksheets():
        df_raw = pd.DataFrame(ws.get_all_values())
        if df_raw.empty: continue

        # Détection automatique de l'en-tête
        header_idx = 0
        for i, row in df_raw.iterrows():
            if "commune" in str(row.values).lower():
                header_idx = i
                break
        
        # Nettoyage des colonnes (fusion des lignes d'en-tête)
        h1 = df_raw.iloc[header_idx]
        h2 = df_raw.iloc[header_idx + 1] if (header_idx + 1) < len(df_raw) else h1
        
        new_cols = []
        curr = ""
        for c1, c2 in zip(h1, h2):
            c1, c2 = str(c1).strip(), str(c2).strip()
            if c1 != "": curr = c1
            col_name = f"{curr}_{c2}" if c2 != "" and c1 != c2 else curr
            new_cols.append(col_name if col_name != "" else "Info")

        df = df_raw.iloc[header_idx+2:].copy()
        df.columns = new_cols
        
        # Conversion numérique automatique
        for col in df.columns:
            if "Commune" not in col:
                df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '.').str.replace(r'\s+', '', regex=True), errors='ignore')
        
        all_sheets[ws.title] = df.dropna(subset=[df.columns[0]])
    return all_sheets

# --- 3. LOGIQUE SIDEBAR ---
SHEET_ID = "1fVb91z5B-nqOwCCPO5rMK-u9wd2KxDG56FteMaCr63w"

with st.sidebar:
    st.image("https://www.svgrepo.com/show/404631/agriculture.svg", width=80)
    st.title("Agri-Chefchaouen v2")
    st.divider()
    
    menu = st.radio(
        "Navigation",
        ["🏠 Tableau de Bord", "📊 Analyses Avancées", "🤖 Expert IA", "📂 Données Brutes"],
        key="main_nav"
    )
    
    st.divider()
    if st.button("🔄 Forcer la mise à jour"):
        st.cache_data.clear()
        st.rerun()

# Chargement des données
try:
    data = load_all_data(SHEET_ID)
except Exception as e:
    st.error(f"Erreur de connexion : {e}")
    st.stop()

# --- 4. PAGES ---

if menu == "🏠 Tableau de Bord":
    st.title("🏠 Synthèse Provinciale")
    
    # KPIs en haut
    col1, col2, col3, col4 = st.columns(4)
    if "PRODUCTION VEGETALE Céréales" in data:
        df_c = data["PRODUCTION VEGETALE Céréales"]
        col1.metric("Surface Totale Blé (Ha)", f"{df_c['BD_Sup'].sum():,.0f}")
        col2.metric("Rendement Moyen", f"{df_c['BD_Rdt'].mean():.1f} qx/ha")
        col3.metric("Communes Actives", len(df_c))
        col4.metric("Status Campagne", "En cours", delta="Optimiste")

    st.markdown("---")
    
    # Graphique interactif principal
    st.subheader("📊 Comparaison des Rendements par Commune")
    sheet_sel = st.selectbox("Choisir une catégorie", list(data.keys()))
    df_sel = data[sheet_sel]
    
    # On cherche les colonnes de rendement (Rdt)
    rdt_cols = [c for c in df_sel.columns if "Rdt" in c]
    if rdt_cols:
        target_rdt = st.selectbox("Culture", rdt_cols)
        fig = px.bar(df_sel, x="Commune", y=target_rdt, color=target_rdt,
                     color_continuous_scale="Greens", template="plotly_white")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Pas de données de rendement sur cette feuille.")

elif menu == "📊 Analyses Avancées":
    st.title("📊 Corrélation et Distribution")
    
    sheet_name = st.selectbox("Source de données", list(data.keys()), key="adv_sheet")
    df = data[sheet_name]
    
    c1, c2 = st.columns(2)
    
    with c1:
        st.subheader("📈 Courbe de tendance")
        cols_num = df.select_dtypes(include=['number']).columns
        x_axis = st.selectbox("Axe X", df.columns, index=0)
        y_axis = st.selectbox("Axe Y", cols_num)
        fig_scat = px.scatter(df, x=x_axis, y=y_axis, size=y_axis, color="Commune", hover_name="Commune", trendline="ols")
        st.plotly_chart(fig_scat, use_container_width=True)

    with c2:
        st.subheader("🥧 Répartition Partielle")
        fig_pie = px.pie(df.head(10), values=y_axis, names="Commune", hole=0.4)
        st.plotly_chart(fig_pie, use_container_width=True)

elif menu == "🤖 Expert IA":
    st.title("🤖 Assistant IA Décisionnel")
    st.markdown("Posez vos questions sur les tendances agricoles de la province.")

    if "gemini_api_key" not in st.secrets:
        st.warning("Veuillez ajouter 'gemini_api_key' dans les secrets.")
    else:
        genai.configure(api_key=st.secrets["gemini_api_key"])
        model = genai.GenerativeModel('gemini-1.5-flash')

        if "messages" not in st.session_state:
            st.session_state.messages = []

        for m in st.session_state.messages:
            with st.chat_message(m["role"]): st.markdown(m["content"])

        if prompt := st.chat_input("Ex: Quelle commune a le meilleur rendement en Olivier ?"):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)

            # Envoi d'un mini-contexte pour aider l'IA
            context = f"Données de la feuille sélectionnée: {data[list(data.keys())[0]].head(10).to_string()}"
            
            with st.chat_message("assistant"):
                with st.spinner("Analyse en cours..."):
                    response = model.generate_content(f"{context}\n\nQuestion: {prompt}")
                    st.markdown(response.text)
                    st.session_state.messages.append({"role": "assistant", "content": response.text})

elif menu == "📂 Données Brutes":
    st.title("📂 Explorateur de Fichiers")
    sel = st.selectbox("Sélectionner la table", list(data.keys()))
    st.dataframe(data[sel], use_container_width=True)