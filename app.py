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

# Style CSS pour un look professionnel
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

        # Détection de l'en-tête (cherche la ligne contenant 'Commune')
        header_idx = 0
        for i, row in df_raw.iterrows():
            if "commune" in str(row.values).lower():
                header_idx = i
                break
        
        # Fusion des en-têtes (Ligne titre + Ligne unité)
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
        
        # --- CORRECTION ICI : Conversion numérique colonne par colonne ---
        for col in df.columns:
            if "Commune" not in col:
                # On nettoie les espaces et remplace les virgules par des points
                df[col] = (df[col].astype(str)
                           .str.replace(r'\s+', '', regex=True)
                           .str.replace(',', '.')
                           .replace('', '0'))
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        
        all_sheets[ws.title] = df.dropna(subset=[df.columns[0]])
    return all_sheets

# --- 3. INITIALISATION ---
SHEET_ID = "1fVb91z5B-nqOwCCPO5rMK-u9wd2KxDG56FteMaCr63w"

# Chargement des données
try:
    data = load_all_data(SHEET_ID)
except Exception as e:
    st.error(f"Erreur lors du chargement des données : {e}")
    st.stop()

# --- 4. SIDEBAR ---
with st.sidebar:
    st.image("https://www.svgrepo.com/show/404631/agriculture.svg", width=80)
    st.title("Agri-Chefchaouen")
    st.divider()
    menu = st.radio("Navigation", ["🏠 Accueil", "📊 Graphiques", "🤖 Expert IA"])
    st.divider()
    if st.button("🔄 Actualiser"):
        st.cache_data.clear()
        st.rerun()

# --- 5. PAGES ---

if menu == "🏠 Accueil":
    st.title("🌿 Tableau de Bord Agricole")
    
    # KPIs dynamiques
    if "PRODUCTION VEGETALE Céréales" in data:
        df_c = data["PRODUCTION VEGETALE Céréales"]
        col1, col2, col3 = st.columns(3)
        with col1: st.metric("Surface Blé Dur (Ha)", f"{df_c['BD_Sup'].sum():,.0f}")
        with col2: st.metric("Rendement Moyen BD", f"{df_c['BD_Rdt'].mean():.1f} qx/ha")
        with col3: st.metric("Nb Communes", len(df_c))

    st.divider()
    st.subheader("Aperçu rapide des données")
    sheet_sel = st.selectbox("Sélectionner une catégorie", list(data.keys()))
    st.dataframe(data[sheet_sel], use_container_width=True)

elif menu == "📊 Graphiques":
    st.title("📊 Analyses Visuelles")
    sheet_sel = st.selectbox("Données à analyser", list(data.keys()))
    df = data[sheet_sel]
    
    # Choix des colonnes numériques pour le graphique
    num_cols = [c for c in df.columns if c != "Commune"]
    target = st.selectbox("Variable à afficher", num_cols)
    
    fig = px.bar(df, x="Commune", y=target, color=target, 
                 title=f"Répartition de : {target}",
                 color_continuous_scale="Viridis", template="plotly_white")
    st.plotly_chart(fig, use_container_width=True)

    

elif menu == "🤖 Expert IA":
    st.title("🤖 Expert IA")
    
    if "gemini_api_key" not in st.secrets:
        st.error("Clé 'gemini_api_key' introuvable dans les secrets.")
    else:
        genai.configure(api_key=st.secrets["gemini_api_key"])
        model = genai.GenerativeModel('gemini-1.5-flash')

        if "messages" not in st.session_state:
            st.session_state.messages = []

        for m in st.session_state.messages:
            with st.chat_message(m["role"]): st.markdown(m["content"])

        if prompt := st.chat_input("Posez votre question..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)

            # Création du contexte pour l'IA
            current_df = data[list(data.keys())[0]].head(10).to_string()
            full_prompt = f"Voici les 10 premières lignes des données : \n{current_df}\n\nQuestion : {prompt}"

            with st.chat_message("assistant"):
                with st.spinner("L'expert réfléchit..."):
                    try:
                        response = model.generate_content(full_prompt)
                        st.markdown(response.text)
                        st.session_state.messages.append({"role": "assistant", "content": response.text})
                    except Exception as e:
                        st.error(f"Erreur IA : {e}")