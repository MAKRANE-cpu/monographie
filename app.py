import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
import re

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Agri-Dashboard Chefchaouen", page_icon="🌿", layout="wide")

# --- 2. NETTOYAGE NUMÉRIQUE ---
def clean_val(val):
    if val is None or val == "":
        return 0.0
    # On force en string, on remplace la virgule par le point, on enlève les espaces
    s = str(val).strip().replace(' ', '').replace('\xa0', '').replace(',', '.')
    # On extrait le nombre
    match = re.search(r"[-+]?\d*\.\d+|\d+", s)
    if match:
        try: return float(match.group())
        except: return 0.0
    return 0.0

@st.cache_data(ttl=600)
def load_all_data(sheet_id):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    sh = client.open_by_key(sheet_id)
    
    all_data = {}
    for ws in sh.worksheets():
        # ÉTAPE CLÉ : On récupère les valeurs en LISTE de LISTES (Python pur)
        # Cela évite que Pandas n'intervienne trop tôt et cause l'erreur "Ambiguous"
        raw_data = ws.get_all_values()
        if not raw_data: continue
        
        # Trouver la ligne d'en-tête
        header_idx = -1
        for i, row in enumerate(raw_data):
            # row est une liste Python simple ici, donc pas d'ambiguïté
            row_lower = [str(cell).lower().strip() for cell in row]
            if "commune" in row_lower:
                header_idx = i
                break
        
        if header_idx == -1: continue

        # Reconstruction des colonnes (Gestion des en-têtes sur 2 lignes)
        h1 = raw_data[header_idx]
        h2 = raw_data[header_idx + 1] if (header_idx + 1) < len(raw_data) else h1
        
        new_cols = []
        current_cat = ""
        for c1, c2 in zip(h1, h2):
            c1, c2 = c1.strip(), c2.strip()
            if c1 != "": current_cat = c1
            
            if c1.lower() == "commune" or c2.lower() == "commune":
                new_cols.append("Commune")
            elif c2 != "" and current_cat != "":
                new_cols.append(f"{current_cat}_{c2}")
            else:
                new_cols.append(current_cat if current_cat else "Info")

        # Création du DataFrame final à partir des données sous l'en-tête
        df = pd.DataFrame(raw_data[header_idx+2:], columns=new_cols)
        
        # Nettoyage des colonnes (sauf Commune)
        for col in df.columns:
            if col != "Commune":
                df[col] = df[col].apply(clean_val)
        
        all_data[ws.title] = df.reset_index(drop=True)
    return all_data

# --- 3. LOGIQUE APP ---
SHEET_ID = "1fVb91z5B-nqOwCCPO5rMK-u9wd2KxDG56FteMaCr63w"

try:
    data_dict = load_all_data(SHEET_ID)
except Exception as e:
    st.error(f"Erreur de chargement : {e}")
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
    st.header("📊 Analyses")
    if data_dict:
        onglet = st.selectbox("Catégorie", list(data_dict.keys()))
        df = data_dict[onglet]
        
        num_cols = [c for c in df.columns if c != "Commune"]
        if num_cols:
            target = st.selectbox("Donnée à afficher", num_cols)
            
            # Graphique professionnel
            fig = px.bar(df, x="Commune", y=target, color=target, 
                         color_continuous_scale="Viridis", 
                         title=f"Répartition par Commune : {target}")
            st.plotly_chart(fig, use_container_width=True)
            
            # KPI
            st.metric("Total Province", f"{df[target].sum():,.2f}")
    else:
        st.warning("Aucune donnée valide trouvée.")

elif page == "🤖 Expert IA":
    st.header("🤖 Expert IA")
    # Logique IA simplifiée
    if "gemini_api_key" in st.secrets:
        genai.configure(api_key=st.secrets["gemini_api_key"])
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = st.chat_input("Question sur les données ?")
        if prompt:
            context = list(data_dict.values())[0].head(5).to_string()
            res = model.generate_content(f"Données : {context}\n\nQuestion : {prompt}")
            st.markdown(res.text)

elif page == "📂 Données Brutes":
    st.header("📂 Tableaux de données")
    onglet = st.selectbox("Feuille", list(data_dict.keys()), key="raw")
    st.dataframe(data_dict[onglet], use_container_width=True)