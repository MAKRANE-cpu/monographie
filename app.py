import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
import google.generativeai as genai
import re
from datetime import datetime
import json
from io import BytesIO
import warnings
warnings.filterwarnings('ignore')

# --- CONFIGURATION ---
st.set_page_config(
    page_title="Agri-Analytics Chefchaouen",
    page_icon="🌱",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- STYLE PERSONNALISÉ ---
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #2E8B57;
        font-weight: 700;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.5rem;
        color: #3CB371;
        font-weight: 600;
        margin-bottom: 1rem;
    }
    .card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 20px;
        border-left: 5px solid #2E8B57;
    }
    .metric-card {
        background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
        border-radius: 10px;
        padding: 15px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .stButton>button {
        background-color: #2E8B57;
        color: white;
        font-weight: 600;
        border: none;
        padding: 10px 24px;
        border-radius: 8px;
        transition: all 0.3s;
    }
    .stButton>button:hover {
        background-color: #3CB371;
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
    .sidebar .sidebar-content {
        background-color: #f8f9fa;
    }
</style>
""", unsafe_allow_html=True)

# --- FONCTIONS UTILITAIRES ---
def clean_val(val):
    """Nettoyage robuste des valeurs numériques"""
    if pd.isna(val) or val in ["", None]:
        return 0.0
    s = str(val).strip()
    s = re.sub(r'[\s\xa0,]+', '', s)
    match = re.search(r"[-+]?\d*\.?\d+", s)
    return float(match.group()) if match else 0.0

def process_sheet_data(raw_data):
    """Traitement intelligent des données d'une feuille"""
    if not raw_data:
        return pd.DataFrame()
    
    # Chercher la ligne avec "Commune"
    header_idx = None
    for i, row in enumerate(raw_data[:10]):
        row_lower = [str(cell).lower().strip() for cell in row]
        if "commune" in row_lower:
            header_idx = i
            break
    
    if header_idx is None:
        return pd.DataFrame()
    
    # Prendre les deux lignes suivantes comme en-têtes
    headers = raw_data[header_idx:header_idx+2]
    
    # Construire les noms de colonnes
    col_names = []
    max_cols = max(len(h) for h in headers)
    
    for i in range(max_cols):
        main = headers[0][i] if i < len(headers[0]) else ""
        sub = headers[1][i] if len(headers) > 1 and i < len(headers[1]) else ""
        
        main_str = str(main).strip()
        sub_str = str(sub).strip()
        
        if main_str and sub_str and main_str != sub_str:
            col_name = f"{main_str} - {sub_str}"
        elif main_str:
            col_name = main_str
        elif sub_str:
            col_name = sub_str
        else:
            col_name = f"Colonne_{i+1}"
        
        col_names.append(col_name)
    
    # Prendre les données à partir de la ligne 3
    data_start = header_idx + 2
    data_rows = raw_data[data_start:] if data_start < len(raw_data) else []
    
    # Créer le DataFrame
    df = pd.DataFrame(data_rows, columns=col_names)
    
    # Nettoyage des données
    for col in df.columns:
        if 'commune' not in col.lower():
            df[col] = df[col].apply(clean_val)
    
    # Nettoyer la colonne Commune
    if 'Commune' in df.columns:
        df['Commune'] = df['Commune'].astype(str).str.strip()
        # Supprimer les lignes de total
        df = df[~df['Commune'].str.contains('total|TOTAL|S/T|munici', case=False, na=False)]
        df = df[df['Commune'] != '']
    
    return df

# --- CHARGEMENT DES DONNÉES ---
@st.cache_data(ttl=600)
def load_data():
    """Charge les données depuis Google Sheets"""
    try:
        SHEET_ID = "1fVb91z5B-nqOwCCPO5rMK-u9wd2KxDG56FteMaCr63w"
        
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        # Utilisation des secrets Streamlit
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"], 
            scopes=scope
        )
        
        client = gspread.authorize(creds)
        sh = client.open_by_key(SHEET_ID)
        
        all_data = {}
        
        for ws in sh.worksheets():
            try:
                # Obtenir toutes les valeurs
                raw = ws.get_all_values()
                
                if not raw:
                    continue
                
                df = process_sheet_data(raw)
                
                if df.empty or len(df) < 2:
                    continue
                
                all_data[ws.title] = df
                
            except Exception as e:
                continue
        
        return all_data
        
    except Exception as e:
        st.error(f"Erreur de chargement : {str(e)}")
        return {}

# --- ANALYSE SPÉCIFIQUE DES TOMATES ---
def analyze_tomato_production(data_dict):
    """Analyse spécifique de la production de tomates"""
    
    results = {
        'communes': [],
        'surface_totale': 0,
        'meilleures_communes': [],
        'recommandations': []
    }
    
    # Chercher les données de tomates
    tomato_data = []
    
    # Chercher dans Maraîchage 1
    if 'Maraîchage 1' in data_dict:
        df = data_dict['Maraîchage 1']
        
        # Chercher les colonnes liées aux tomates
        for col in df.columns:
            if 'tomate' in col.lower():
                # Chercher les colonnes de surface
                if any(x in col.lower() for x in ['sup', 'ha', 'surface']):
                    for _, row in df.iterrows():
                        commune = row.get('Commune', 'Inconnue')
                        surface = row[col]
                        
                        if pd.notna(surface) and surface > 0:
                            tomato_data.append({
                                'commune': commune,
                                'surface_tomate': surface,
                                'source': 'Maraîchage 1'
                            })
    
    # Chercher dans Maraichage 2
    if 'Maraichage 2' in data_dict:
        df = data_dict['Maraichage 2']
        
        for col in df.columns:
            if 'tomate' in col.lower():
                if any(x in col.lower() for x in ['sup', 'ha', 'surface']):
                    for _, row in df.iterrows():
                        commune = row.get('Commune', 'Inconnue')
                        surface = row[col]
                        
                        if pd.notna(surface) and surface > 0:
                            tomato_data.append({
                                'commune': commune,
                                'surface_tomate': surface,
                                'source': 'Maraichage 2'
                            })
    
    # Chercher dans Maraichage 3
    if 'Maraichage 3' in data_dict:
        df = data_dict['Maraichage 3']
        
        for col in df.columns:
            if 'tomate' in col.lower():
                if any(x in col.lower() for x in ['sup', 'ha', 'surface']):
                    for _, row in df.iterrows():
                        commune = row.get('Commune', 'Inconnue')
                        surface = row[col]
                        
                        if pd.notna(surface) and surface > 0:
                            tomato_data.append({
                                'commune': commune,
                                'surface_tomate': surface,
                                'source': 'Maraichage 3'
                            })
    
    # Analyser les données collectées
    if tomato_data:
        df_tomato = pd.DataFrame(tomato_data)
        
        # Agréger par commune
        commune_stats = df_tomato.groupby('commune').agg({
            'surface_tomate': 'sum'
        }).reset_index()
        
        # Trier par surface
        commune_stats = commune_stats.sort_values('surface_tomate', ascending=False)
        
        results['communes'] = commune_stats.to_dict('records')
        results['surface_totale'] = commune_stats['surface_tomate'].sum()
        
        # Top 3 des communes
        if len(commune_stats) > 0:
            results['meilleures_communes'] = commune_stats.head(3).to_dict('records')
            
            # Recommandations
            results['recommandations'].append(f"**Commune prioritaire**: {commune_stats.iloc[0]['commune']} avec {commune_stats.iloc[0]['surface_tomate']} ha de tomates")
            
            if len(commune_stats) > 1:
                results['recommandations'].append(f"**Second choix**: {commune_stats.iloc[1]['commune']} ({commune_stats.iloc[1]['surface_tomate']} ha)")
            
            if len(commune_stats) > 2:
                results['recommandations'].append(f"**Troisième option**: {commune_stats.iloc[2]['commune']} ({commune_stats.iloc[2]['surface_tomate']} ha)")
    
    return results

# --- INITIALISATION ---
# Initialisation de la session state pour la navigation
if 'page' not in st.session_state:
    st.session_state.page = "Accueil"

# Chargement des données
@st.cache_data(ttl=600)
def load_cached_data():
    return load_data()

# --- SIDEBAR ---
with st.sidebar:
    st.markdown('<div class="main-header">🌿 Navigation</div>', unsafe_allow_html=True)
    
    # Navigation avec des boutons qui changent st.session_state.page
    if st.button("🏠 Accueil", use_container_width=True):
        st.session_state.page = "Accueil"
    
    if st.button("🍅 Analyse Tomates", use_container_width=True):
        st.session_state.page = "Tomates"
    
    if st.button("📊 Visualisations", use_container_width=True):
        st.session_state.page = "Visualisations"
    
    if st.button("🤖 Assistant IA", use_container_width=True):
        st.session_state.page = "Assistant IA"
    
    if st.button("⚙️ Exploration Données", use_container_width=True):
        st.session_state.page = "Données"
    
    st.divider()
    
    # Chargement des données avec indicateur
    with st.spinner("Chargement des données..."):
        data_dict = load_cached_data()
    
    if data_dict:
        total_communes = set()
        for df in data_dict.values():
            if 'Commune' in df.columns:
                communes = df['Commune'].dropna().unique()
                total_communes.update(communes)
        
        st.metric("Communes analysées", len(total_communes))
        st.metric("Jeux de données", len(data_dict))
    
    st.divider()
    
    if st.button("🔄 Actualiser les données", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- PAGE ACCUEIL ---
if st.session_state.page == "Accueil":
    st.markdown('<div class="main-header">🌱 Agri-Analytics Chefchaouen</div>', unsafe_allow_html=True)
    
    if not data_dict:
        st.error("❌ Impossible de charger les données. Vérifiez la connexion et les permissions.")
        st.stop()
    
    st.success(f"✅ {len(data_dict)} feuilles chargées avec succès!")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("""
        ### 📊 Plateforme d'Aide à la Décision Agricole
        
        Cette application vous permet d'analyser les données agricoles de la province de Chefchaouen
        pour prendre des décisions éclairées.
        
        **Données disponibles:**
        - Superficies agricoles
        - Production végétale (céréales, légumineuses, maraîchage)
        - Production animale
        - Irrigation
        - Données pédologiques
        - Population agricole
        
        **Exemples d'analyses possibles:**
        - Identifier les communes les plus productives
        - Optimiser les cultures par zone
        - Planifier les investissements en irrigation
        - Développer des filières agricoles
        """)
    
    with col2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown("### 🚀 Accès rapide")
        
        if st.button("🍅 Analyser les tomates"):
            st.session_state.page = "Tomates"
            st.rerun()
        
        if st.button("📈 Voir visualisations"):
            st.session_state.page = "Visualisations"
            st.rerun()
        
        if st.button("🤖 Poser une question"):
            st.session_state.page = "Assistant IA"
            st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Aperçu des données
    st.divider()
    st.markdown("### 📋 Aperçu des données disponibles")
    
    # Afficher les premières feuilles
    sheet_list = list(data_dict.keys())
    
    for i in range(0, min(6, len(sheet_list)), 2):
        cols = st.columns(2)
        for j in range(2):
            if i + j < len(sheet_list):
                sheet_name = sheet_list[i + j]
                df = data_dict[sheet_name]
                with cols[j]:
                    with st.expander(f"📄 {sheet_name} ({len(df)} lignes)"):
                        st.dataframe(df.head(5), use_container_width=True, height=200)

# --- PAGE ANALYSE TOMATES ---
elif st.session_state.page == "Tomates":
    st.markdown('<div class="main-header">🍅 Analyse de la Production de Tomates</div>', unsafe_allow_html=True)
    
    if not data_dict:
        st.error("Données non chargées")
        st.stop()
    
    # Analyse des données de tomates
    with st.spinner("Analyse des données de tomates en cours..."):
        tomato_analysis = analyze_tomato_production(data_dict)
    
    if not tomato_analysis['communes']:
        st.warning("""
        ⚠️ **Données de tomates limitées**
        
        Les données spécifiques sur la production de tomates sont limitées dans les feuilles chargées.
        
        **Consultez ces feuilles pour plus d'informations:**
        """)
        
        # Lister les feuilles de maraîchage disponibles
        maraichage_sheets = [s for s in data_dict.keys() if 'maraichage' in s.lower() or 'maraîchage' in s.lower()]
        
        if maraichage_sheets:
            for sheet in maraichage_sheets:
                with st.expander(f"📄 {sheet}"):
                    df = data_dict[sheet]
                    st.dataframe(df.head(), use_container_width=True)
        else:
            st.info("Aucune feuille de maraîchage trouvée")
            
        # Alternative : analyser les données d'irrigation pour les communes prometteuses
        st.markdown("### 💡 Approche alternative")
        st.markdown("""
        Pour développer la culture de tomates, considérez ces critères:
        
        1. **Irrigation disponible** (feuille "L'IRRIGATION")
        2. **Expérience en maraîchage** (feuilles de maraîchage)
        3. **Accès aux marchés**
        4. **Coopératives existantes**
        
        **Communes recommandées pour investigation:**
        - Bab Taza (plus grande commune)
        - Tanaqob (bonne irrigation)
        - Bab Bared (expérience agricole)
        """)
    else:
        # Affichage des résultats
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("Surface totale de tomates", f"{tomato_analysis['surface_totale']:.1f} ha")
            st.metric("Communes productrices", len(tomato_analysis['communes']))
        
        with col2:
            if tomato_analysis['meilleures_communes']:
                top_commune = tomato_analysis['meilleures_communes'][0]
                st.metric("Meilleure commune", top_commune['commune'])
                st.caption(f"{top_commune['surface_tomate']:.1f} ha de surface")
        
        # Réponse à la question
        st.markdown("---")
        st.markdown("### 🎯 Réponse à votre question:")
        
        if tomato_analysis['meilleures_communes']:
            top_commune = tomato_analysis['meilleures_communes'][0]
            
            st.success(f"""
            ## 🥇 **Commune prioritaire: {top_commune['commune']}**
            
            **Pourquoi commencer par {top_commune['commune']} ?**
            
            1. **Expérience existante**: Cette commune a déjà {top_commune['surface_tomate']} ha de tomates cultivées
            2. **Savoir-faire local**: Les agriculteurs ont déjà l'expertise technique
            3. **Infrastructures**: Possibilité d'utiliser les circuits de distribution existants
            4. **Rendements connus**: Meilleure prévision des résultats
            
            **Actions recommandées:**
            - Organiser des formations spécifiques sur l'amélioration des rendements
            - Mettre en place une coopérative de producteurs de tomates
            - Développer un système d'irrigation optimisé
            - Créer une marque "Tomates de {top_commune['commune']}"
            """)
            
            # Graphique des meilleures communes
            st.markdown("### 📈 Classement des communes productrices de tomates")
            
            top_df = pd.DataFrame(tomato_analysis['meilleures_communes'])
            fig = px.bar(
                top_df,
                x='commune',
                y='surface_tomate',
                title="Top des communes par surface de tomates",
                color='surface_tomate',
                color_continuous_scale="reds",
                text='surface_tomate'
            )
            fig.update_traces(texttemplate='%{text:.1f} ha', textposition='outside')
            st.plotly_chart(fig, use_container_width=True)
            
            # Tableau complet
            st.markdown("### 📋 Toutes les communes productrices")
            all_df = pd.DataFrame(tomato_analysis['communes'])
            st.dataframe(
                all_df.sort_values('surface_tomate', ascending=False),
                use_container_width=True
            )
    
    # Bouton de retour
    st.markdown("---")
    if st.button("← Retour à l'accueil"):
        st.session_state.page = "Accueil"
        st.rerun()

# --- PAGE VISUALISATIONS ---
elif st.session_state.page == "Visualisations":
    st.markdown('<div class="main-header">📊 Visualisations des Données Agricoles</div>', unsafe_allow_html=True)
    
    if not data_dict:
        st.warning("Aucune donnée disponible pour la visualisation")
        st.stop()
    
    # Sélection de la feuille
    selected_sheet = st.selectbox(
        "Sélectionnez une feuille de données",
        list(data_dict.keys())
    )
    
    if selected_sheet:
        df = data_dict[selected_sheet]
        
        # Vérifier les colonnes
        if df.empty:
            st.warning("Cette feuille ne contient pas de données")
            st.stop()
        
        # Colonnes disponibles
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        commune_col = None
        
        for col in df.columns:
            if 'commune' in col.lower():
                commune_col = col
                break
        
        if not commune_col:
            st.warning("Colonne 'Commune' non trouvée dans cette feuille")
            st.dataframe(df, use_container_width=True)
            st.stop()
        
        if not numeric_cols:
            st.warning("Aucune colonne numérique trouvée")
            st.dataframe(df, use_container_width=True)
            st.stop()
        
        # Interface de visualisation
        col1, col2 = st.columns([1, 3])
        
        with col1:
            selected_col = st.selectbox(
                "Sélectionnez une variable à visualiser",
                numeric_cols
            )
            
            chart_type = st.selectbox(
                "Type de graphique",
                ["Barres verticales", "Barres horizontales", "Camembert"]
            )
            
            sort_order = st.selectbox(
                "Trier par",
                ["Valeur décroissante", "Valeur croissante", "Nom de commune"]
            )
            
            top_n = st.slider("Nombre de communes à afficher", 5, 30, 15)
        
        with col2:
            # Préparation des données
            plot_data = df[[commune_col, selected_col]].copy()
            plot_data = plot_data.dropna()
            
            # Trier selon la sélection
            if sort_order == "Valeur décroissante":
                plot_data = plot_data.sort_values(selected_col, ascending=False)
            elif sort_order == "Valeur croissante":
                plot_data = plot_data.sort_values(selected_col, ascending=True)
            else:  # Ordre alphabétique
                plot_data = plot_data.sort_values(commune_col)
            
            # Limiter le nombre d'éléments
            plot_data = plot_data.head(top_n)
            
            # Création du graphique
            if chart_type == "Barres verticales":
                fig = px.bar(
                    plot_data,
                    x=commune_col,
                    y=selected_col,
                    title=f"{selected_col} par commune",
                    color=selected_col,
                    color_continuous_scale="greens",
                    text=selected_col
                )
                fig.update_traces(texttemplate='%{text:.0f}', textposition='outside')
                fig.update_layout(xaxis_tickangle=-45)
            
            elif chart_type == "Barres horizontales":
                fig = px.bar(
                    plot_data,
                    y=commune_col,
                    x=selected_col,
                    title=f"{selected_col} par commune",
                    color=selected_col,
                    color_continuous_scale="greens",
                    text=selected_col,
                    orientation='h'
                )
                fig.update_traces(texttemplate='%{text:.0f}', textposition='outside')
            
            else:  # Camembert
                fig = px.pie(
                    plot_data,
                    values=selected_col,
                    names=commune_col,
                    title=f"Répartition de {selected_col}"
                )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Statistiques
            with st.expander("📊 Statistiques détaillées"):
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Total", f"{plot_data[selected_col].sum():,.0f}")
                col2.metric("Moyenne", f"{plot_data[selected_col].mean():,.1f}")
                col3.metric("Minimum", f"{plot_data[selected_col].min():,.0f}")
                col4.metric("Maximum", f"{plot_data[selected_col].max():,.0f}")
    
    # Bouton de retour
    st.markdown("---")
    if st.button("← Retour à l'accueil"):
        st.session_state.page = "Accueil"
        st.rerun()

# --- PAGE ASSISTANT IA ---
elif st.session_state.page == "Assistant IA":
    st.markdown('<div class="main-header">🤖 Assistant Agricole Intelligent</div>', unsafe_allow_html=True)
    
    # Initialisation de l'historique de chat
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    
    # Vérification de l'API Gemini
    api_available = "gemini_api_key" in st.secrets
    
    if not api_available:
        st.warning("""
        ⚠️ **Mode Analyse Automatique Activé**
        
        L'API Gemini n'est pas configurée. Vous pouvez toujours poser des questions,
        mais les réponses seront basées sur l'analyse automatique des données disponibles.
        
        Pour activer l'IA avancée, ajoutez dans `.streamlit/secrets.toml`:
        ```toml
        gemini_api_key = "votre_cle_api_ici"
        ```
        
        **En attendant, voici des analyses disponibles:**
        """)
        
        # Afficher les analyses automatiques
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🍅 Analyser les tomates", use_container_width=True):
                st.session_state.page = "Tomates"
                st.rerun()
        
        with col2:
            if st.button("📊 Voir les données", use_container_width=True):
                st.session_state.page = "Données"
                st.rerun()
    
    # Zone de chat
    st.markdown("### 💬 Posez votre question sur l'agriculture à Chefchaouen")
    
    # Suggestions de questions
    st.markdown("#### 💡 Suggestions:")
    
    suggestions = st.columns(2)
    
    with suggestions[0]:
        if st.button("Meilleures communes pour tomates", use_container_width=True):
            st.session_state.user_question = "Quelles sont les meilleures communes pour développer la culture de tomates ?"
    
    with suggestions[1]:
        if st.button("Potentiel d'irrigation", use_container_width=True):
            st.session_state.user_question = "Quelles communes ont le meilleur potentiel d'irrigation ?"
    
    # Affichage de l'historique
    for message in st.session_state.chat_history[-10:]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # Saisie utilisateur
    user_input = st.chat_input("Écrivez votre question ici...")
    
    # Utiliser la question stockée ou la saisie
    if 'user_question' in st.session_state:
        user_input = st.session_state.user_question
        del st.session_state.user_question
    
    if user_input:
        # Ajouter la question à l'historique
        st.session_state.chat_history.append({"role": "user", "content": user_input})
        
        with st.chat_message("user"):
            st.markdown(user_input)
        
        # Réponse de l'assistant
        with st.chat_message("assistant"):
            with st.spinner("Analyse en cours..."):
                try:
                    if api_available:
                        # Essayer avec Gemini
                        genai.configure(api_key=st.secrets["gemini_api_key"])
                        
                        # Essayer différents modèles
                        try:
                            model = genai.GenerativeModel('gemini-pro')
                        except:
                            # Essayer avec un autre modèle
                            try:
                                model = genai.GenerativeModel('models/gemini-pro')
                            except:
                                # Dernier essai
                                model = genai.GenerativeModel('gemini-1.0-pro')
                        
                        # Préparer le contexte
                        context = "Données agricoles de Chefchaouen disponibles. "
                        context += f"Nombre de feuilles: {len(data_dict)}. "
                        
                        # Ajouter des informations spécifiques sur les tomates si la question est liée
                        if 'tomate' in user_input.lower():
                            tomato_analysis = analyze_tomato_production(data_dict)
                            if tomato_analysis['meilleures_communes']:
                                context += f"Top communes pour tomates: {tomato_analysis['meilleures_communes'][0]['commune']}. "
                        
                        prompt = f"""
                        Tu es un expert agronome spécialisé dans la province de Chefchaouen au Maroc.
                        
                        CONTEXTE: {context}
                        
                        QUESTION: {user_input}
                        
                        Réponds en français avec:
                        1. Des recommandations pratiques
                        2. Des communes spécifiques si pertinentes
                        3. Des actions concrètes
                        4. Des considérations techniques
                        
                        Sois précis et utile.
                        """
                        
                        response = model.generate_content(prompt)
                        answer = response.text
                        
                    else:
                        # Réponse automatique basée sur les données
                        if 'tomate' in user_input.lower():
                            tomato_analysis = analyze_tomato_production(data_dict)
                            if tomato_analysis['meilleures_communes']:
                                top = tomato_analysis['meilleures_communes'][0]
                                answer = f"""
                                **🍅 Analyse des tomates à Chefchaouen**
                                
                                **Commune prioritaire:** {top['commune']} avec {top['surface_tomate']} ha
                                
                                **Recommandations:**
                                1. Commencer par {top['commune']} où l'expérience existe déjà
                                2. Développer l'irrigation dans cette zone
                                3. Former les agriculteurs aux techniques modernes
                                4. Créer une coopérative dédiée
                                
                                **Prochaines étapes:**
                                - Analyser les données d'irrigation de {top['commune']}
                                - Évaluer les besoins en formation
                                - Identifier les débouchés commerciaux
                                """
                            else:
                                answer = """
                                **🍅 Culture de tomates à Chefchaouen**
                                
                                **Approche recommandée:**
                                1. Commencer par Bab Taza (plus grande commune)
                                2. S'appuyer sur l'expérience existante en maraîchage
                                3. Développer l'irrigation en priorité
                                4. Former les agriculteurs aux bonnes pratiques
                                
                                **Feuilles à consulter:**
                                - L'IRRIGATION pour l'eau disponible
                                - Maraîchage 1, 2, 3 pour l'expérience existante
                                - COOPERATIVES pour les organisations existantes
                                """
                        else:
                            # Réponse générique
                            answer = f"""
                            **🌾 Analyse agricole de Chefchaouen**
                            
                            **Pour répondre à: "{user_input}"**
                            
                            **Données disponibles:** {len(data_dict)} feuilles avec informations sur:
                            - Superficies agricoles
                            - Production végétale et animale
                            - Irrigation
                            - Coopératives
                            - Données pédologiques
                            
                            **Pour une analyse précise:**
                            1. Consultez la page "🍅 Analyse Tomates" pour le maraîchage
                            2. Utilisez "📊 Visualisations" pour les analyses graphiques
                            3. Explorez "⚙️ Exploration Données" pour les données brutes
                            
                            **Questions spécifiques recommandées:**
                            - "Quelles communes ont le plus de potentiel pour [culture]?"
                            - "Comment améliorer l'irrigation à [commune]?"
                            - "Quelles coopératives existent pour [produit]?"
                            """
                    
                    st.markdown(answer)
                    st.session_state.chat_history.append({"role": "assistant", "content": answer})
                    
                except Exception as e:
                    # Réponse de secours en cas d'erreur
                    error_answer = f"""
                    **🔧 Analyse automatique**
                    
                    **Question:** {user_input}
                    
                    **Réponse basée sur les données disponibles:**
                    
                    Pour développer l'agriculture à Chefchaouen, je vous recommande de:
                    
                    1. **Consulter les données spécifiques** dans les autres pages
                    2. **Analyser les tendances** par commune
                    3. **Étudier l'irrigation disponible**
                    4. **S'appuyer sur les coopératives existantes**
                    
                    **Pour les tomates en particulier:**
                    - Consultez la page "🍅 Analyse Tomates"
                    - Étudiez les données d'irrigation
                    - Analysez l'expérience existante en maraîchage
                    
                    *Note: Pour des analyses plus avancées, configurez l'API Gemini.*
                    """
                    
                    st.markdown(error_answer)
                    st.session_state.chat_history.append({"role": "assistant", "content": error_answer})
    
    # Bouton de retour
    st.markdown("---")
    if st.button("← Retour à l'accueil", key="back_from_ai"):
        st.session_state.page = "Accueil"
        st.rerun()

# --- PAGE EXPLORATION DONNÉES ---
else:  # Données
    st.markdown('<div class="main-header">⚙️ Exploration des Données Agricoles</div>', unsafe_allow_html=True)
    
    if not data_dict:
        st.warning("Aucune donnée disponible")
        st.stop()
    
    # Sélection de la feuille
    selected_sheet = st.selectbox(
        "Sélectionnez une feuille à explorer",
        list(data_dict.keys()),
        key="data_explorer"
    )
    
    if selected_sheet:
        df = data_dict[selected_sheet]
        
        # Informations sur la feuille
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Lignes", len(df))
        
        with col2:
            st.metric("Colonnes", len(df.columns))
        
        with col3:
            if 'Commune' in df.columns:
                communes = df['Commune'].nunique()
                st.metric("Communes", communes)
            else:
                st.metric("Col. Commune", "Non trouvée")
        
        with col4:
            numeric_cols = len(df.select_dtypes(include=[np.number]).columns)
            st.metric("Col. numériques", numeric_cols)
        
        # Affichage des données
        st.markdown("### 📋 Données brutes")
        
        tab1, tab2 = st.tabs(["Tableau complet", "Statistiques"])
        
        with tab1:
            # Options d'affichage
            col1, col2 = st.columns(2)
            
            with col1:
                rows_to_show = st.slider("Lignes à afficher", 10, 100, 20, key="rows_slider")
            
            with col2:
                show_all_cols = st.checkbox("Afficher toutes les colonnes", value=True)
            
            if show_all_cols:
                st.dataframe(df.head(rows_to_show), use_container_width=True)
            else:
                # Afficher seulement les premières colonnes
                display_cols = list(df.columns[:min(8, len(df.columns))])
                st.dataframe(df[display_cols].head(rows_to_show), use_container_width=True)
                
                if len(df.columns) > 8:
                    st.caption(f"Affichage des 8 premières colonnes sur {len(df.columns)}. Cochez la case pour tout voir.")
        
        with tab2:
            # Statistiques descriptives
            numeric_df = df.select_dtypes(include=[np.number])
            
            if not numeric_df.empty:
                st.dataframe(numeric_df.describe(), use_container_width=True)
                
                # Export des statistiques
                stats_csv = numeric_df.describe().to_csv()
                st.download_button(
                    label="📥 Télécharger les statistiques (CSV)",
                    data=stats_csv,
                    file_name=f"statistiques_{selected_sheet}.csv",
                    mime="text/csv"
                )
            else:
                st.info("Aucune colonne numérique pour les statistiques")
        
        # Export des données
        st.markdown("---")
        st.markdown("### 📤 Export des données")
        
        col1, col2 = st.columns(2)
        
        with col1:
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Télécharger en CSV",
                data=csv,
                file_name=f"{selected_sheet}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col2:
            # Export Excel
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Données')
            excel_data = output.getvalue()
            
            st.download_button(
                label="📊 Télécharger en Excel",
                data=excel_data,
                file_name=f"{selected_sheet}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
    
    # Bouton de retour
    st.markdown("---")
    if st.button("← Retour à l'accueil", key="back_from_data"):
        st.session_state.page = "Accueil"
        st.rerun()

# --- FOOTER ---
st.divider()
st.caption(f"Agri-Analytics Chefchaouen • Données: {len(data_dict)} feuilles • {datetime.now().strftime('%Y-%m-%d %H:%M')}")