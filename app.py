import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
import re

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Agri-Chefchaouen Dashboard", page_icon="🌿", layout="wide")

# --- 2. FONCTION DE NETTOYAGE ROBUSTE ---
def clean_val(val):
    if val is None or val == "":
        return 0.0
    # Nettoyage des caractères spéciaux et espaces
    s = str(val).strip().replace(' ', '').replace('\xa0', '').replace(',', '.')
    # Extraction du nombre (gestion des cas comme "12.5 quintaux")
    match = re.search(r"[-+]?\d*\.\d+|\d+", s)
    if match:
        try:
            return float(match.group())
        except:
            return 0.0
    return 0.0

@st.cache_data(ttl=600)
def load_and_fix_data(sheet_id):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    sh = client.open_by_key(sheet_id)
    
    all_data = {}
    for ws in sh.worksheets():
        rows = ws.get_all_values()
        if not rows: continue
        
        df_raw = pd.DataFrame(rows)
        
        # --- CORRECTION DE L'ERREUR DE CONNEXION ---
        header_idx = 0
        for i, row in df_raw.iterrows():
            # On vérifie si "commune" est présent dans AU MOINS UN élément de la ligne
            if any("commune" in str(v).lower() for v in row):
                header_idx = i
                break
        
        # Reconstruction des colonnes (Gestion des en-têtes fusionnés)
        h1 = df_raw.iloc[header_idx]
        h2 = df_raw.iloc[header_idx + 1] if (header_idx + 1) < len(df_raw) else h1
        
        new_cols = []
        current_main = ""
        for c1, c2 in zip(h1, h2):
            c1, c2 = str(c1).strip(), str(c2).strip()
            if c1 != "" and "unnamed" not in c1.lower():
                current_main = c1
            
            if "commune" in c1.lower() or "commune" in c2.lower():
                new_cols.append("Commune")
            elif c2 != "" and current_main != "":
                new_cols.append(f"{current_main}_{c2}")
            else:
                new_cols.append(current_main if current_main else "Info")
        
        df = df_raw.iloc[header_idx+2:].copy()
        df.columns = new_cols
        
        # Nettoyage numérique sécurisé
        for col in df.columns:
            if "Commune" not in col:
                df[col] = df[col].apply(clean_val)
        
        all_data[ws.title] = df.reset_index(drop=True)
    return all_data

# --- 3. CHARGEMENT ET INTERFACE ---
SHEET_ID = "1fVb91z5B-nqOwCCPO5rMK-u9wd2KxDG56FteMaCr63w"

try:
    data_dict = load_and_fix_data(SHEET_ID)
except Exception as e:
    st.error(f"Erreur de connexion : {e}")
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.title("🌿 Agri-Chefchaouen")
    page = st.radio("Menu", ["📊 Dashboard", "🤖 Expert IA", "📂 Données Brutes"])
    if st.button("🔄 Actualiser"):
        st.cache_data.clear()
        st.rerun()

# --- PAGES ---
if page == "📊 Dashboard":
    st.title("📊 Analyses des Productions")
    onglet = st.selectbox("Choisir une feuille", list(data_dict.keys()))
    df = data_dict[onglet]
    
    num_cols = [c for c in df.columns if c != "Commune"]
    if num_cols:
        target = st.selectbox("Variable à analyser", num_cols)
        
        # KPIs
        col1, col2 = st.columns(2)
        col1.metric("Total", f"{df[target].sum():,.0f}")
        col2.metric("Moyenne", f"{df[target].mean():.2f}")
        
        # Graphique
        fig = px.bar(df, x="Commune", y=target, color=target, 
                     color_continuous_scale="Greens", 
                     title=f"Répartition par Commune : {target}")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Aucune donnée numérique détectée.")

elif page == "🤖 Expert IA":
    st.title("🤖 Expert IA")
    # (Le code IA reste le même que précédemment)
    if "gemini_api_key" in st.secrets:
        genai.configure(api_key=st.secrets["gemini_api_key"])
        model = genai.GenerativeModel('gemini-1.5-flash')
        # ... logique de chat ...
        prompt = st.chat_input("Posez votre question...")
        if prompt:
            res = model.generate_content(f"Données: {df.head().to_string()}\n\nQuestion: {prompt}")
            st.write(res.text)

elif page == "📂 Données Brutes":
    st.title("📂 Explorateur")
    onglet = st.selectbox("Feuille", list(data_dict.keys()))
    st.dataframe(data_dict[onglet], use_container_width=True)