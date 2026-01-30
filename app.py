import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai

# --- 1. CONFIGURATION DE LA PAGE ---
st.set_page_config(
    page_title="Agri-Chefchaouen Data", 
    page_icon="🌿", 
    layout="wide"
)

# --- 2. FONCTION DE CHARGEMENT ET NETTOYAGE ---
@st.cache_data(ttl=600)
def load_gspread_data(sheet_id):
    # Authentification
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(creds)
    
    sh = client.open_by_key(sheet_id)
    worksheets = sh.worksheets()
    
    all_data = {}
    
    for ws in worksheets:
        values = ws.get_all_values()
        if not values:
            continue
            
        df_raw = pd.DataFrame(values)
        
        # --- DÉTECTION DYNAMIQUE DE L'EN-TÊTE ---
        # On cherche la ligne qui contient "Commune"
        header_idx = None
        for i, row in df_raw.iterrows():
            if any("commune" in str(v).lower() for v in row.values):
                header_idx = i
                break
        
        if header_idx is not None:
            # Ligne principale (ex: Culture ou Commune)
            h_names = df_raw.iloc[header_idx]
            # Ligne secondaire (ex: Sup / Rdt)
            h_units = df_raw.iloc[header_idx + 1] if (header_idx + 1) < len(df_raw) else None
            
            new_cols = []
            current_main = ""
            
            for idx, col_name in enumerate(h_names):
                col_name = str(col_name).strip()
                unit_name = str(h_units[idx]).strip() if h_units is not None else ""
                
                # Si la case du haut n'est pas vide, c'est une nouvelle culture
                if col_name != "" and "unnamed" not in col_name.lower():
                    current_main = col_name
                
                if "commune" in col_name.lower() or "commune" in unit_name.lower():
                    new_cols.append("Commune")
                elif unit_name != "" and current_main != "":
                    # On fusionne Culture + Unité (ex: Fève_Sup)
                    new_cols.append(f"{current_main}_{unit_name}")
                elif current_main != "":
                    new_cols.append(current_main)
                else:
                    new_cols.append(f"Col_{idx}")

            df_raw.columns = new_cols
            # On garde les données après les en-têtes (index + 2)
            df = df_raw.iloc[header_idx + 2:].reset_index(drop=True)
        else:
            # Cas de secours si "Commune" n'est pas trouvé
            df = df_raw.copy()
            df.columns = df.iloc[0]
            df = df[1:].reset_index(drop=True)

        # Nettoyage final
        df = df.loc[:, ~df.columns.duplicated()] # Supprime colonnes en double
        all_data[ws.title] = df
        
    return all_data

# --- 3. LOGIQUE DE LA BARRE LATÉRALE (SIDEBAR) ---
# Un seul bloc pour éviter les erreurs de duplication d'ID
SHEET_ID = "1fVb91z5B-nqOwCCPO5rMK-u9wd2KxDG56FteMaCr63w"

with st.sidebar:
    st.title("🌿 Agri-Chefchaouen")
    
    # Bouton de mise à jour forcée
    if st.button("🔄 Actualiser les données", key="refresh_data"):
        st.cache_data.clear()
        st.success("Données synchronisées !")
        st.rerun()
    
    st.divider()
    
    # Navigation principale
    page = st.radio(
        "Menu", 
        ["📊 Tableaux de Bord", "🤖 Expert IA", "📈 Graphiques"],
        key="nav_radio"
    )

# --- 4. CHARGEMENT INITIAL DES DONNÉES ---
try:
    data_dict = load_gspread_data(SHEET_ID)
except Exception as e:
    st.error(f"Impossible de charger Google Sheets : {e}")
    st.stop()

# --- 5. CONTENU DES PAGES ---

if page == "📊 Tableaux de Bord":
    st.header("Visualisation des données")
    
    onglet = st.selectbox("Sélectionner une feuille", list(data_dict.keys()), key="select_sheet")
    df_display = data_dict[onglet].copy()
    
    # Tentative de conversion numérique pour les calculs/affichage
    for col in df_display.columns:
        if col != "Commune":
            df_display[col] = pd.to_numeric(
                df_display[col].astype(str).str.replace(',', '.').str.replace(r'\s+', '', regex=True), 
                errors='ignore'
            )
    
    st.dataframe(df_display, use_container_width=True)

elif page == "🤖 Expert IA":
    st.header("Assistant Intelligent")
    # Configuration Gemini (remplacez par votre clé)
    genai.configure(api_key=st.secrets["gemini_api_key"])
    model = genai.GenerativeModel('gemini-1.5-pro')
    
    user_query = st.text_input("Posez votre question sur l'agriculture à Chefchaouen :")
    if user_query:
        # On prépare un petit contexte avec les premières lignes de la feuille active
        context = data_dict[list(data_dict.keys())[0]].head(10).to_string()
        response = model.generate_content(f"Contexte : {context}\n\nQuestion : {user_query}")
        st.markdown(response.text)

elif page == "📈 Graphiques":
    st.header("Analyses Graphiques")
    # Exemple avec la première feuille
    sheet_name = list(data_dict.keys())[0]
    df_graph = data_dict[sheet_name].copy()
    
    # Nettoyage rapide pour graphique
    col_x = "Commune"
    col_y = st.selectbox("Choisir une colonne pour le graphique", [c for c in df_graph.columns if c != "Commune"])
    
    if col_y:
        df_graph[col_y] = pd.to_numeric(df_graph[col_y].astype(str).str.replace(',', '.'), errors='coerce')
        fig = st.bar_chart(df_graph, x=col_x, y=col_y)