import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
import re

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Agri-Chefchaouen Dashboard", page_icon="🌿", layout="wide")

# --- 2. NETTOYAGE NUMÉRIQUE ---
def clean_val(val):
    if val is None or val == "":
        return 0.0
    s = str(val).strip().replace(' ', '').replace('\xa0', '').replace(',', '.')
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
        # Récupérer les données sous forme de liste de listes (évite l'ambiguïté Pandas au départ)
        raw_rows = ws.get_all_values()
        if not raw_rows: continue
        
        # --- DÉTECTION DE L'EN-TÊTE SÉCURISÉE ---
        header_idx = None
        for i, row in enumerate(raw_rows):
            # On cherche "commune" dans la liste Python native
            row_lower = [str(cell).lower().strip() for cell in row]
            if "commune" in row_lower:
                header_idx = i
                break
        
        if header_idx is None:
            continue # On ignore cette feuille si "Commune" n'est pas trouvé

        # Reconstruction des noms de colonnes
        h1 = raw_rows[header_idx]
        h2 = raw_rows[header_idx + 1] if (header_idx + 1) < len(raw_rows) else h1
        
        new_cols = []
        current_culture = ""
        for c1, c2 in zip(h1, h2):
            c1, c2 = c1.strip(), c2.strip()
            if c1 != "":
                current_culture = c1
            
            if c1.lower() == "commune" or c2.lower() == "commune":
                new_cols.append("Commune")
            elif c2 != "" and current_culture != "":
                new_cols.append(f"{current_culture}_{c2}")
            else:
                new_cols.append(current_culture if current_culture else "Info")
        
        # Création du DataFrame final
        df = pd.DataFrame(raw_rows[header_idx + 2:], columns=new_cols)
        
        # Nettoyage des colonnes numériques
        for col in df.columns:
            if col != "Commune":
                df[col] = df[col].apply(clean_val)
        
        all_data[ws.title] = df.reset_index(drop=True)
    return all_data

# --- 3. LOGIQUE D'AFFICHAGE ---
SHEET_ID = "1fVb91z5B-nqOwCCPO5rMK-u9wd2KxDG56FteMaCr63w"

try:
    data_dict = load_and_fix_data(SHEET_ID)
except Exception as e:
    st.error(f"Erreur technique : {e}")
    st.stop()

# --- INTERFACE ---
with st.sidebar:
    st.title("🌿 Agri-Chefchaouen")
    page = st.radio("Navigation", ["📊 Dashboard", "🤖 Expert IA", "📂 Données Brutes"])
    if st.button("🔄 Actualiser les données"):
        st.cache_data.clear()
        st.rerun()

if page == "📊 Dashboard":
    st.header("📊 Analyses des Productions")
    if not data_dict:
        st.warning("Aucune donnée valide n'a pu être chargée. Vérifiez que le mot 'Commune' est présent dans vos feuilles.")
    else:
        onglet = st.selectbox("Sélectionner une catégorie", list(data_dict.keys()))
        df = data_dict[onglet]
        
        num_cols = [c for c in df.columns if c != "Commune"]
        if num_cols:
            target = st.selectbox("Choisir la donnée à analyser", num_cols)
            
            # Affichage des KPIs
            kpi1, kpi2 = st.columns(2)
            kpi1.metric("Cumul Province", f"{df[target].sum():,.0f}")
            kpi2.metric("Moyenne / Commune", f"{df[target].mean():.2f}")
            
            # Graphique interactif
            fig = px.bar(df, x="Commune", y=target, color=target, 
                         color_continuous_scale="Viridis",
                         title=f"Répartition par Commune : {target}")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Cette feuille ne contient pas de colonnes numériques exploitables.")

elif page == "🤖 Expert IA":
    st.header("🤖 Expert IA")
    if "gemini_api_key" in st.secrets:
        genai.configure(api_key=st.secrets["gemini_api_key"])
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = st.chat_input("Posez votre question sur les données agricoles...")
        if prompt:
            # Envoi du contexte (extrait des données)
            sample = list(data_dict.values())[0].head(5).to_string()
            response = model.generate_content(f"Données : {sample}\nQuestion : {prompt}")
            st.markdown(response.text)
    else:
        st.error("Clé API Gemini manquante.")

elif page == "📂 Données Brutes":
    st.header("📂 Explorateur de données")
    onglet = st.selectbox("Feuille", list(data_dict.keys()), key="raw_view")
    st.dataframe(data_dict[onglet], use_container_width=True)