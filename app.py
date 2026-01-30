import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
import re

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Agri-Dashboard Chefchaouen", page_icon="🌿", layout="wide")

# --- 2. FONCTION DE NETTOYAGE NUMÉRIQUE ---
def clean_val(val):
    """Transforme n'importe quelle cellule en nombre flottant propre"""
    if val is None or val == "":
        return 0.0
    # Nettoyage : point à la place de virgule, suppression des espaces
    s = str(val).strip().replace(' ', '').replace('\xa0', '').replace(',', '.')
    # Extraction du premier nombre trouvé
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
        # Utiliser get_all_values() qui renvoie une liste de listes (Python pur)
        # Cela évite les erreurs d'ambiguïté de Pandas lors de la détection
        raw_rows = ws.get_all_values()
        if not raw_rows: continue
        
        # --- RÉSOLUTION DE L'ERREUR AMBIGUOUS ---
        header_idx = None
        for i, row in enumerate(raw_rows):
            # On cherche "commune" dans la ligne (insensible à la casse)
            row_lower = [str(cell).lower().strip() for cell in row]
            if "commune" in row_lower:
                header_idx = i
                break
        
        if header_idx is None:
            continue

        # Reconstruction des noms de colonnes (Gestion des cellules fusionnées)
        h1 = raw_rows[header_idx]
        h2 = raw_rows[header_idx + 1] if (header_idx + 1) < len(raw_rows) else h1
        
        new_cols = []
        current_culture = ""
        for c1, c2 in zip(h1, h2):
            c1, c2 = str(c1).strip(), str(c2).strip()
            if c1 != "":
                current_culture = c1
            
            if c1.lower() == "commune" or c2.lower() == "commune":
                new_cols.append("Commune")
            elif c2 != "" and current_culture != "":
                new_cols.append(f"{current_culture}_{c2}")
            else:
                new_cols.append(current_culture if current_culture else "Info")
        
        # Création du DataFrame à partir des lignes de données uniquement
        df = pd.DataFrame(raw_rows[header_idx+2:], columns=new_cols)
        
        # Nettoyage des chiffres colonne par colonne
        for col in df.columns:
            if col != "Commune":
                df[col] = df[col].apply(clean_val)
        
        all_data[ws.title] = df.reset_index(drop=True)
    return all_data

# --- 3. LOGIQUE DE NAVIGATION ---
SHEET_ID = "1fVb91z5B-nqOwCCPO5rMK-u9wd2KxDG56FteMaCr63w"

try:
    data_dict = load_and_fix_data(SHEET_ID)
except Exception as e:
    st.error(f"Erreur technique lors du chargement : {e}")
    st.stop()

with st.sidebar:
    st.title("🌿 Agri-Chefchaouen")
    page = st.radio("Menu", ["📊 Dashboard", "🤖 Expert IA", "📂 Données Brutes"])
    if st.button("🔄 Actualiser les données"):
        st.cache_data.clear()
        st.rerun()

# --- 4. PAGES ---

if page == "📊 Dashboard":
    st.title("📊 Analyses des Productions")
    if not data_dict:
        st.warning("Aucune feuille avec une colonne 'Commune' n'a été trouvée.")
    else:
        onglet = st.selectbox("Choisir une feuille", list(data_dict.keys()))
        df = data_dict[onglet]
        
        num_cols = [c for c in df.columns if c != "Commune"]
        if num_cols:
            target = st.selectbox("Variable à visualiser", num_cols)
            
            c1, c2 = st.columns(2)
            c1.metric("Total Province", f"{df[target].sum():,.0f}")
            c2.metric("Moyenne / Commune", f"{df[target].mean():.2f}")
            
            fig = px.bar(df, x="Commune", y=target, color=target, 
                         color_continuous_scale="Greens",
                         title=f"Répartition de {target} par commune")
            st.plotly_chart(fig, use_container_width=True)

elif page == "🤖 Expert IA":
    st.title("🤖 Assistant IA")
    if "gemini_api_key" in st.secrets:
        genai.configure(api_key=st.secrets["gemini_api_key"])
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = st.chat_input("Posez votre question...")
        if prompt:
            sample = list(data_dict.values())[0].head(5).to_string()
            response = model.generate_content(f"Données: {sample}\n\nQuestion: {prompt}")
            st.write(response.text)

elif page == "📂 Données Brutes":
    st.title("📂 Explorateur")
    onglet = st.selectbox("Feuille", list(data_dict.keys()), key="raw_view")
    st.dataframe(data_dict[onglet], use_container_width=True)