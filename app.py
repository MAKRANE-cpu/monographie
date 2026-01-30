import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
import re

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Agri-Chefchaouen Dashboard", page_icon="🌿", layout="wide")

# --- 2. FONCTION DE NETTOYAGE ULTRA-ROBUSTE ---
def clean_val(val):
    """Transforme n'importe quelle cellule en nombre propre"""
    if val is None or val == "":
        return 0.0
    # Nettoyage : point à la place de virgule, suppression des espaces
    s = str(val).strip().replace(' ', '').replace('\xa0', '').replace(',', '.')
    # On extrait uniquement les chiffres et le point décimal
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
        
        # --- RÉPARATION DE L'ERREUR 'AMBIGUOUS' ---
        header_idx = 0
        found_header = False
        for i, row in df_raw.iterrows():
            # Correction : on teste chaque cellule individuellement
            # On utilise une compréhension de liste avec any() pour éviter l'ambiguïté
            if any("commune" in str(v).lower() for v in row.values):
                header_idx = i
                found_header = True
                break
        
        if not found_header:
            continue

        # Reconstruction des noms de colonnes (Gestion des cellules fusionnées)
        h1 = df_raw.iloc[header_idx]
        h2 = df_raw.iloc[header_idx + 1] if (header_idx + 1) < len(df_raw) else h1
        
        new_cols = []
        current_culture = ""
        for c1, c2 in zip(h1, h2):
            c1, c2 = str(c1).strip(), str(c2).strip()
            if c1 != "" and "unnamed" not in c1.lower():
                current_culture = c1
            
            if "commune" in c1.lower() or "commune" in c2.lower():
                new_cols.append("Commune")
            elif c2 != "" and current_culture != "":
                new_cols.append(f"{current_culture}_{c2}")
            else:
                new_cols.append(current_culture if current_culture else "Info")
        
        df = df_raw.iloc[header_idx+2:].copy()
        df.columns = new_cols
        
        # Nettoyage des chiffres colonne par colonne
        for col in df.columns:
            if "Commune" not in col:
                df[col] = df[col].apply(clean_val)
        
        all_data[ws.title] = df.reset_index(drop=True)
    return all_data

# --- 3. CHARGEMENT ET NAVIGATION ---
SHEET_ID = "1fVb91z5B-nqOwCCPO5rMK-u9wd2KxDG56FteMaCr63w"

try:
    data_dict = load_and_fix_data(SHEET_ID)
except Exception as e:
    st.error(f"Erreur technique lors du chargement : {e}")
    st.stop()

with st.sidebar:
    st.title("🌿 Agri-Chefchaouen")
    page = st.radio("Menu", ["📊 Dashboard", "🤖 Expert IA", "📂 Données Brutes"])
    if st.button("🔄 Actualiser"):
        st.cache_data.clear()
        st.rerun()

# --- 4. PAGES ---
if page == "📊 Dashboard":
    st.title("📊 Analyses des Productions")
    onglet = st.selectbox("Choisir une feuille", list(data_dict.keys()))
    df = data_dict[onglet]
    
    num_cols = [c for c in df.columns if c != "Commune"]
    if num_cols:
        target = st.selectbox("Variable à visualiser", num_cols)
        
        # KPIs simples
        c1, c2 = st.columns(2)
        c1.metric("Total", f"{df[target].sum():,.0f}")
        c2.metric("Moyenne", f"{df[target].mean():.2f}")
        
        # Graphique Plotly
        fig = px.bar(df, x="Commune", y=target, color=target, 
                     color_continuous_scale="Greens", 
                     title=f"Distribution de {target} par commune")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Aucune donnée chiffrée exploitable trouvée ici.")

elif page == "🤖 Expert IA":
    st.title("🤖 Assistant IA")
    if "gemini_api_key" in st.secrets:
        genai.configure(api_key=st.secrets["gemini_api_key"])
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        prompt = st.chat_input("Ex: Quel est le rendement moyen des céréales ?")
        if prompt:
            # On donne un contexte à l'IA avec les premières lignes
            ctx = data_dict[list(data_dict.keys())[0]].head(5).to_string()
            response = model.generate_content(f"Données: {ctx}\n\nQuestion: {prompt}")
            st.write(response.text)
    else:
        st.error("Clé API absente des secrets.")

elif page == "📂 Données Brutes":
    st.title("📂 Explorateur")
    onglet = st.selectbox("Feuille", list(data_dict.keys()))
    st.dataframe(data_dict[onglet], use_container_width=True)