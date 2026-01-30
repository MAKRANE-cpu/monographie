import streamlit as st
import pandas as pd
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai

# --- 1. CONFIGURATION DE LA PAGE ---
st.set_page_config(page_title="Agri-Chefchaouen Data", page_icon="🌿", layout="wide")

# Style CSS pour améliorer l'interface
st.markdown("""
    <style>
    .main { background-color: #f9fbf9; }
    h1, h2 { color: #2e7d32; }
    .stDataFrame { border: 1px solid #e0e0e0; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- 2. CONNEXION GOOGLE SHEETS ---
@st.cache_data(ttl=600)
def load_gspread_data(sheet_id):
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    # Utilisation des secrets Streamlit pour les credentials GCP
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    
    sh = client.open_by_key(sheet_id)
    worksheets = sh.worksheets()
    
    all_data = {}
    for ws in worksheets:
        # Récupère toutes les valeurs
        values = ws.get_all_values()
        if not values:
            continue
            
        # Création du DataFrame
        df = pd.DataFrame(values)
        
        # Nettoyage automatique : on cherche la ligne qui contient "Commune" 
        # car vos fichiers ont souvent des lignes vides au début
        header_idx = 0
        for i, row in df.iterrows():
            if "Commune" in row.values or "communes" in row.values:
                header_idx = i
                break
        
        df.columns = df.iloc[header_idx]
        df = df.iloc[header_idx + 1:].reset_index(drop=True)
        # Supprimer les colonnes vides
        df = df.loc[:, df.columns.notna()]
        all_data[ws.title] = df
        
    return all_data

SHEET_ID = "1fVb91z5B-nqOwCCPO5rMK-u9wd2KxDG56FteMaCr63w"

try:
    data_dict = load_gspread_data(SHEET_ID)
except Exception as e:
    st.error(f"Erreur de connexion : {e}")
    st.info("Vérifiez la configuration de vos 'Secrets' sur Streamlit Cloud.")
    st.stop()

# --- 3. CONFIGURATION IA (GEMINI) ---
genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
ai_model = genai.GenerativeModel('gemini-1.5-flash')

# --- 4. BARRE LATÉRALE ---
with st.sidebar:
    st.title("🌿 Agri-Chefchaouen")
    st.write("Analyse de la Monographie")
    st.markdown("---")
    page = st.radio("Menu", ["📊 Tableaux de Bord", "🤖 Expert IA", "📈 Graphiques"])

# --- 5. PAGES ---

if page == "📊 Tableaux de Bord":
    st.title("Exploration des Données")
    onglet = st.selectbox("Choisir une catégorie (Onglet)", list(data_dict.keys()))
    
    df_display = data_dict[onglet]
    st.write(f"Données pour : **{onglet}**")
    st.dataframe(df_display, use_container_width=True)
    
    st.download_button("📥 Télécharger en CSV", df_display.to_csv(index=False), "data.csv")

elif page == "🤖 Expert IA":
    st.title("Assistant IA Agricole")
    st.info("Posez des questions sur les surfaces, les types de sols ou les productions de Chefchaouen.")
    
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    prompt = st.chat_input("Ex: Quelle commune a la plus grande surface irriguée ?")
    
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
            
        # Préparation du contexte IA (échantillon des données)
        context = ""
        for name, df in data_dict.items():
            context += f"\nFeuille {name}:\n{df.head(5).to_string()}\n"

        full_query = f"Données provinciales :\n{context}\n\nQuestion : {prompt}"
        
        with st.chat_message("assistant"):
            response = ai_model.generate_content(full_query)
            st.markdown(response.text)
            st.session_state.messages.append({"role": "assistant", "content": response.text})

elif page == "📈 Graphiques":
    st.title("Visualisation Interactive")
    onglet = st.selectbox("Sélectionner la donnée à visualiser", list(data_dict.keys()))
    df = data_dict[onglet]
    
    # Nettoyage des données numériques pour les graphiques
    for col in df.columns:
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '.'), errors='ignore')

    cols_numeriques = df.select_dtypes(include=['number']).columns.tolist()
    
    if len(cols_numeriques) > 0:
        c1, c2 = st.columns(2)
        with c1:
            y_col = st.selectbox("Valeur à analyser (Y)", cols_numeriques)
        with c2:
            chart_type = st.selectbox("Type de graphique", ["Barres", "Secteurs"])
            
        if chart_type == "Barres":
            fig = px.bar(df, x="Commune" if "Commune" in df.columns else df.columns[0], 
                         y=y_col, color=y_col, title=f"{y_col} par Commune")
        else:
            fig = px.pie(df, names="Commune" if "Commune" in df.columns else df.columns[0], 
                         values=y_col, title=f"Répartition de {y_col}")
            
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Pas de données numériques détectées dans cet onglet pour créer un graphique.")