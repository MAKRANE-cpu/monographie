"""
Application Web d'Intelligence Agricole pour la Province de Chefchaouen
Dashboard décisionnel avec visualisations interactives, chatbot RAG et génération de monographie
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import gspread
from google.oauth2.service_account import Credentials
import os
try:
    from langchain_experimental.agents import create_pandas_dataframe_agent
    from langchain_openai import ChatOpenAI
    from langchain.schema import HumanMessage, SystemMessage
except ImportError:
    try:
        from langchain.agents import create_pandas_dataframe_agent
        from langchain.chat_models import ChatOpenAI
        from langchain.schema import HumanMessage, SystemMessage
    except ImportError:
        st.error("Erreur d'importation LangChain. Veuillez installer: pip install langchain langchain-experimental langchain-openai")
        st.stop()
import json
from datetime import datetime
import warnings
from dotenv import load_dotenv
warnings.filterwarnings('ignore')

# Chargement des variables d'environnement
load_dotenv()

# Configuration de la page
st.set_page_config(
    page_title="Intelligence Agricole - Chefchaouen",
    page_icon="🌾",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Variables de session pour le cache
if 'dataframes' not in st.session_state:
    st.session_state.dataframes = {}
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'monographie' not in st.session_state:
    st.session_state.monographie = None

# Fonction pour charger les données depuis Google Sheets
@st.cache_data(ttl=3600)  # Cache pour 1 heure
def load_google_sheets_data(credentials_path, spreadsheet_identifier, use_id=False):
    """
    Charge les données depuis Google Sheets
    
    Args:
        credentials_path: Chemin vers le fichier JSON des credentials Google
        spreadsheet_identifier: Nom ou ID du fichier Google Sheets
        use_id: Si True, utilise l'ID au lieu du nom
    
    Returns:
        dict: Dictionnaire avec les noms des feuilles comme clés et les DataFrames comme valeurs
    """
    try:
        # Configuration des scopes
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        # Chargement des credentials
        creds = Credentials.from_service_account_file(
            credentials_path,
            scopes=scopes
        )
        
        # Connexion à Google Sheets
        client = gspread.authorize(creds)
        
        # Ouverture du fichier par ID ou par nom
        if use_id:
            spreadsheet = client.open_by_key(spreadsheet_identifier)
        else:
            spreadsheet = client.open(spreadsheet_identifier)
        
        # Récupération de toutes les feuilles
        dataframes = {}
        for sheet in spreadsheet.worksheets():
            try:
                data = sheet.get_all_records()
                if data:
                    df = pd.DataFrame(data)
                    # Nettoyage des noms de colonnes
                    df.columns = df.columns.str.strip()
                    dataframes[sheet.title] = df
            except Exception as e:
                st.warning(f"Erreur lors du chargement de la feuille '{sheet.title}': {str(e)}")
        
        return dataframes
    
    except Exception as e:
        st.error(f"Erreur lors de la connexion à Google Sheets: {str(e)}")
        return {}

# Fonction pour créer des visualisations
def create_visualizations(df, sheet_name):
    """
    Crée des visualisations interactives selon le type de données
    """
    if df.empty:
        st.warning(f"La feuille '{sheet_name}' est vide.")
        return
    
    st.subheader(f"📊 Visualisations - {sheet_name}")
    
    # Détection automatique du type de données
    numeric_cols = df.select_dtypes(include=['float64', 'int64']).columns.tolist()
    text_cols = df.select_dtypes(include=['object']).columns.tolist()
    
    # Si on détecte des colonnes de type culture/superficie/production
    if any(keyword in sheet_name.lower() for keyword in ['culture', 'production', 'rendement']):
        create_agricultural_charts(df, numeric_cols, text_cols)
    elif any(keyword in sheet_name.lower() for keyword in ['climat', 'meteo', 'temperature']):
        create_climate_charts(df, numeric_cols)
    elif any(keyword in sheet_name.lower() for keyword in ['eau', 'water', 'irrigation']):
        create_water_charts(df, numeric_cols, text_cols)
    elif any(keyword in sheet_name.lower() for keyword in ['parcelle', 'terrain']):
        create_parcel_charts(df, numeric_cols, text_cols)
    else:
        create_generic_charts(df, numeric_cols, text_cols)

def create_agricultural_charts(df, numeric_cols, text_cols):
    """Visualisations spécifiques pour les données agricoles"""
    col1, col2 = st.columns(2)
    
    with col1:
        # Recherche de colonnes pertinentes
        surface_col = next((col for col in df.columns if 'surface' in col.lower() or 'superficie' in col.lower() or 'ha' in col.lower()), None)
        production_col = next((col for col in df.columns if 'production' in col.lower() or 'tonne' in col.lower()), None)
        culture_col = next((col for col in df.columns if 'culture' in col.lower() or 'type' in col.lower() or 'variete' in col.lower()), None)
        
        if culture_col and surface_col:
            # Graphique en barres des superficies par culture
            fig = px.bar(
                df.groupby(culture_col)[surface_col].sum().reset_index(),
                x=culture_col,
                y=surface_col,
                title=f"Superficie par type de culture",
                labels={culture_col: "Type de culture", surface_col: "Superficie (HA)"},
                color=surface_col,
                color_continuous_scale="Greens"
            )
            fig.update_layout(showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        
        if culture_col and production_col:
            # Graphique de production par culture
            fig = px.pie(
                df.groupby(culture_col)[production_col].sum().reset_index(),
                values=production_col,
                names=culture_col,
                title=f"Répartition de la production par culture"
            )
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        # Graphique combiné superficie/production
        if surface_col and production_col and culture_col:
            grouped = df.groupby(culture_col).agg({
                surface_col: 'sum',
                production_col: 'sum'
            }).reset_index()
            
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            
            fig.add_trace(
                go.Bar(x=grouped[culture_col], y=grouped[surface_col], name="Superficie (HA)", marker_color='lightgreen'),
                secondary_y=False,
            )
            
            fig.add_trace(
                go.Scatter(x=grouped[culture_col], y=grouped[production_col], name="Production (T)", marker_color='darkgreen', mode='lines+markers'),
                secondary_y=True,
            )
            
            fig.update_xaxes(title_text="Type de culture")
            fig.update_yaxes(title_text="Superficie (HA)", secondary_y=False)
            fig.update_yaxes(title_text="Production (T)", secondary_y=True)
            fig.update_layout(title_text="Superficie et Production par culture")
            
            st.plotly_chart(fig, use_container_width=True)
        
        # Tableau récapitulatif
        if len(numeric_cols) > 0:
            st.subheader("📋 Statistiques descriptives")
            st.dataframe(df[numeric_cols].describe(), use_container_width=True)

def create_climate_charts(df, numeric_cols):
    """Visualisations pour les données climatiques"""
    if len(numeric_cols) < 1:
        return
    
    # Recherche de colonnes de température et précipitation
    temp_col = next((col for col in df.columns if 'temp' in col.lower() or 'temperature' in col.lower()), None)
    precip_col = next((col for col in df.columns if 'precip' in col.lower() or 'pluie' in col.lower() or 'mm' in col.lower()), None)
    date_col = next((col for col in df.columns if 'date' in col.lower() or 'mois' in col.lower() or 'annee' in col.lower()), None)
    
    if date_col and (temp_col or precip_col):
        # Graphique temporel
        fig = go.Figure()
        
        if temp_col:
            fig.add_trace(go.Scatter(
                x=df[date_col],
                y=df[temp_col],
                mode='lines+markers',
                name='Température',
                line=dict(color='red', width=2)
            ))
        
        if precip_col:
            fig.add_trace(go.Scatter(
                x=df[date_col],
                y=df[precip_col],
                mode='lines+markers',
                name='Précipitations',
                line=dict(color='blue', width=2),
                yaxis='y2'
            ))
        
        fig.update_layout(
            title="Évolution climatique",
            xaxis_title="Période",
            yaxis_title="Température (°C)" if temp_col else "Valeur",
            yaxis2=dict(title="Précipitations (mm)", overlaying='y', side='right') if precip_col else None,
            hovermode='x unified'
        )
        
        st.plotly_chart(fig, use_container_width=True)
    else:
        # Graphiques génériques
        for col in numeric_cols[:3]:
            fig = px.histogram(df, x=col, title=f"Distribution de {col}")
            st.plotly_chart(fig, use_container_width=True)

def create_water_charts(df, numeric_cols, text_cols):
    """Visualisations pour les ressources en eau"""
    col1, col2 = st.columns(2)
    
    with col1:
        water_col = next((col for col in df.columns if 'eau' in col.lower() or 'water' in col.lower() or 'irrigation' in col.lower()), None)
        if water_col and water_col in numeric_cols:
            fig = px.bar(df, x=df.index, y=water_col, title="Ressources en eau disponibles")
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        if len(numeric_cols) > 0:
            fig = px.box(df, y=numeric_cols[0], title="Distribution des ressources")
            st.plotly_chart(fig, use_container_width=True)

def create_parcel_charts(df, numeric_cols, text_cols):
    """Visualisations pour les parcelles"""
    # Carte ou graphique de répartition géographique si disponible
    st.info("Visualisation des données de parcelles")
    st.dataframe(df, use_container_width=True)

def create_generic_charts(df, numeric_cols, text_cols):
    """Visualisations génériques pour données non catégorisées"""
    if len(numeric_cols) > 0:
        col1, col2 = st.columns(2)
        
        with col1:
            for col in numeric_cols[:2]:
                fig = px.bar(df, x=df.index[:20], y=col, title=f"{col}")
                st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            if len(numeric_cols) > 2:
                fig = px.scatter(df, x=numeric_cols[0], y=numeric_cols[1], title="Relation entre variables")
                st.plotly_chart(fig, use_container_width=True)
    
    st.dataframe(df.head(20), use_container_width=True)

# Fonction pour initialiser l'agent RAG
def initialize_rag_agent(dataframes):
    """
    Initialise l'agent LangChain avec les données des DataFrames
    """
    if not st.session_state.get('openai_api_key'):
        return None
    
    if not dataframes or len(dataframes) == 0:
        return None
    
    try:
        # Filtrer les DataFrames non vides
        valid_dfs = {k: v for k, v in dataframes.items() if not v.empty}
        
        if not valid_dfs:
            return None
        
        # Concaténation de tous les DataFrames pour l'agent
        # Ajouter une colonne pour identifier la source
        dfs_with_source = []
        for sheet_name, df in valid_dfs.items():
            df_copy = df.copy()
            df_copy['_source_sheet'] = sheet_name
            dfs_with_source.append(df_copy)
        
        combined_df = pd.concat(dfs_with_source, ignore_index=True, sort=False)
        
        # Initialisation du LLM
        try:
            llm = ChatOpenAI(
                temperature=0,
                model="gpt-4",
                openai_api_key=st.session_state.openai_api_key
            )
        except TypeError:
            # Fallback pour les anciennes versions
            llm = ChatOpenAI(
                temperature=0,
                model_name="gpt-4",
                openai_api_key=st.session_state.openai_api_key
            )
        
        # Création de l'agent pandas avec gestion des erreurs
        try:
            agent = create_pandas_dataframe_agent(
                llm,
                combined_df,
                verbose=True,
                allow_dangerous_code=False
            )
        except TypeError:
            # Essayer sans le paramètre allow_dangerous_code pour les anciennes versions
            agent = create_pandas_dataframe_agent(
                llm,
                combined_df,
                verbose=True
            )
        
        return agent
    except Exception as e:
        st.error(f"Erreur lors de l'initialisation de l'agent: {str(e)}")
        return None

# Fonction pour le chatbot RAG
def chat_with_rag(question, agent, dataframes):
    """
    Traite une question avec l'agent RAG
    """
    if not agent:
        return "Veuillez configurer votre clé API OpenAI dans les paramètres."
    
    try:
        # Contexte sur les données disponibles
        context = f"""
        Vous êtes un assistant expert en agriculture pour la province de Chefchaouen, Maroc.
        
        Données disponibles dans les feuilles:
        {', '.join(dataframes.keys())}
        
        Si une information n'est pas disponible dans les données fournies, utilisez vos connaissances générales 
        sur l'agriculture au Maroc, la région du Rif, et Chefchaouen pour compléter votre réponse.
        Précisez toujours quand vous utilisez des connaissances générales plutôt que les données du fichier.
        
        Question: {question}
        """
        
        # Essayer différentes méthodes selon les versions de LangChain
        full_question = context + "\n\n" + question
        
        try:
            # Méthode 1 : agent.run() (anciennes versions)
            response = agent.run(full_question)
            return response
        except AttributeError:
            try:
                # Méthode 2 : agent.invoke() (nouvelles versions)
                response = agent.invoke({"input": full_question})
                if isinstance(response, dict):
                    return response.get("output", str(response))
                return str(response)
            except Exception:
                # Méthode 3 : agent() directement
                try:
                    response = agent(full_question)
                    return str(response)
                except Exception as e:
                    return f"Erreur lors du traitement: {str(e)}. Veuillez vérifier votre configuration LangChain."
    except Exception as e:
        return f"Erreur lors du traitement de la question: {str(e)}"

# Fonction pour générer la monographie
def generate_monographie(dataframes):
    """
    Génère une monographie complète de la province de Chefchaouen
    """
    if not st.session_state.get('openai_api_key'):
        return None
    
    try:
        # Préparation des données pour le contexte
        data_summary = {}
        for sheet_name, df in dataframes.items():
            if not df.empty:
                numeric_cols = df.select_dtypes(include=['float64', 'int64']).columns.tolist()
                if numeric_cols:
                    data_summary[sheet_name] = {
                        'columns': df.columns.tolist(),
                        'summary': df[numeric_cols].describe().to_dict(),
                        'sample_data': df.head(5).to_dict('records')
                    }
        
        # Prompt pour la génération de la monographie
        prompt = f"""
        Vous êtes un expert en géographie, agriculture et développement rural au Maroc.
        
        Génère une monographie complète et structurée de la Province de Chefchaouen en suivant cette structure :
        
        1. CADRE GÉOGRAPHIQUE
           - Localisation et limites administratives
           - Topographie (relief montagneux du Rif)
           - Climat et précipitations
           - Hydrographie et ressources en eau
           - Végétation naturelle
        
        2. POTENTIEL AGRICOLE ACTUEL (basé sur les données fournies)
           - Analyse des cultures principales selon les données
           - Superficies cultivées
           - Productions et rendements
           - Systèmes de production (pluvial/irrigué)
           - Spécificités locales (arboriculture, cannabis légal/industriel si applicable)
        
        3. DIAGNOSTIC SWOT
           - Forces (avantages naturels, savoir-faire local)
           - Faiblesses (contraintes topographiques, accès limité, etc.)
           - Opportunités (marchés, programmes de développement)
           - Menaces (changement climatique, érosion, etc.)
        
        4. RECOMMANDATIONS POUR LE DÉVELOPPEMENT RURAL
           - Stratégies d'amélioration de la productivité
           - Diversification des cultures
           - Gestion durable des ressources
           - Valorisation des produits locaux
           - Intégration des nouvelles technologies
        
        Données disponibles dans le fichier :
        {json.dumps(data_summary, indent=2, ensure_ascii=False)}
        
        Si certaines données sont manquantes, utilisez vos connaissances générales sur Chefchaouen et le Rif marocain.
        Intégrez les spécificités de la région : topographie montagneuse, culture pluviale dominante, 
        arboriculture (oliviers, figuiers), et le contexte du développement du cannabis légal/industriel.
        
        Format de sortie : Texte structuré avec titres et sous-titres clairs, en français.
        """
        
        try:
            llm = ChatOpenAI(
                temperature=0.7,
                model="gpt-4",
                openai_api_key=st.session_state.openai_api_key
            )
        except TypeError:
            # Fallback pour les anciennes versions
            llm = ChatOpenAI(
                temperature=0.7,
                model_name="gpt-4",
                openai_api_key=st.session_state.openai_api_key
            )
        
        messages = [
            SystemMessage(content="Vous êtes un expert en géographie et développement rural au Maroc."),
            HumanMessage(content=prompt)
        ]
        
        response = llm(messages)
        return response.content
    
    except Exception as e:
        return f"Erreur lors de la génération de la monographie: {str(e)}"

# Interface principale
def main():
    # Sidebar
    with st.sidebar:
        st.title("🌾 Intelligence Agricole")
        st.subheader("Province de Chefchaouen")
        
        # Configuration
        st.header("⚙️ Configuration")
        
        # Clé API OpenAI (peut être chargée depuis les variables d'environnement)
        default_openai_key = os.getenv('OPENAI_API_KEY', st.session_state.get('openai_api_key', ''))
        openai_key = st.text_input(
            "Clé API OpenAI",
            type="password",
            value=default_openai_key,
            help="Nécessaire pour le chatbot RAG et la génération de monographie. Peut aussi être définie via la variable d'environnement OPENAI_API_KEY"
        )
        st.session_state.openai_api_key = openai_key
        
        # Configuration Google Sheets (peut être chargée depuis les variables d'environnement)
        default_credentials = os.getenv('GOOGLE_CREDENTIALS_PATH', 'credentials.json')
        credentials_path = st.text_input(
            "Chemin du fichier JSON Google Cloud",
            value=default_credentials,
            help="Chemin vers votre fichier de credentials Google Cloud. Peut aussi être défini via la variable d'environnement GOOGLE_CREDENTIALS_PATH"
        )
        
        # Choix entre ID ou nom du fichier
        use_id = st.checkbox(
            "Utiliser l'ID du fichier (recommandé)",
            value=True,
            help="Cochez cette case pour utiliser l'ID du fichier Google Sheets au lieu du nom"
        )
        
        if use_id:
            default_spreadsheet_id = os.getenv('GOOGLE_SPREADSHEET_ID', '1fVb91z5B-nqOwCCPO5rMK-u9wd2KxDG56FteMaCr63w')
            spreadsheet_identifier = st.text_input(
                "ID du fichier Google Sheets",
                value=default_spreadsheet_id,
                help="ID du fichier Google Sheets (visible dans l'URL). Peut aussi être défini via la variable d'environnement GOOGLE_SPREADSHEET_ID"
            )
        else:
            default_spreadsheet = os.getenv('GOOGLE_SPREADSHEET_NAME', '')
            spreadsheet_identifier = st.text_input(
                "Nom du fichier Google Sheets",
                value=default_spreadsheet,
                help="Nom exact du fichier Google Sheets. Peut aussi être défini via la variable d'environnement GOOGLE_SPREADSHEET_NAME"
            )
        
        # Bouton de chargement
        if st.button("🔄 Charger les données", type="primary"):
            if os.path.exists(credentials_path) and spreadsheet_identifier:
                with st.spinner("Chargement des données depuis Google Sheets..."):
                    st.session_state.dataframes = load_google_sheets_data(
                        credentials_path,
                        spreadsheet_identifier,
                        use_id=use_id
                    )
                    if st.session_state.dataframes:
                        st.success(f"✅ {len(st.session_state.dataframes)} feuille(s) chargée(s)")
                    else:
                        st.error("Aucune donnée chargée. Vérifiez vos credentials et l'ID/le nom du fichier.")
            else:
                st.error("Veuillez renseigner le chemin des credentials et l'ID/le nom du fichier.")
        
        st.divider()
        
        # Navigation
        st.header("📑 Navigation")
        page = st.radio(
            "Sélectionnez une section",
            ["Vue d'ensemble", "Analyses par filière", "Assistant IA", "Rapport Monographique"]
        )
    
    # Contenu principal selon la page sélectionnée
    if page == "Vue d'ensemble":
        show_overview()
    elif page == "Analyses par filière":
        show_analysis_by_sector()
    elif page == "Assistant IA":
        show_ai_assistant()
    elif page == "Rapport Monographique":
        show_monographie()

def show_overview():
    """Page Vue d'ensemble"""
    st.title("📊 Vue d'ensemble")
    
    if not st.session_state.dataframes:
        st.info("👆 Veuillez charger les données depuis la barre latérale.")
        return
    
    st.subheader("📁 Feuilles de données disponibles")
    
    # Affichage des statistiques générales
    cols = st.columns(len(st.session_state.dataframes))
    for idx, (sheet_name, df) in enumerate(st.session_state.dataframes.items()):
        with cols[idx % len(cols)]:
            st.metric(
                label=sheet_name,
                value=f"{len(df)} lignes",
                delta=f"{len(df.columns)} colonnes"
            )
    
    # Tableau récapitulatif
    st.subheader("📋 Aperçu des données")
    for sheet_name, df in st.session_state.dataframes.items():
        with st.expander(f"📄 {sheet_name} ({len(df)} lignes)"):
            st.dataframe(df.head(10), use_container_width=True)
            if len(df) > 10:
                st.caption(f"Affiche 10 lignes sur {len(df)}")

def show_analysis_by_sector():
    """Page Analyses par filière"""
    st.title("🔍 Analyses par filière")
    
    if not st.session_state.dataframes:
        st.info("👆 Veuillez charger les données depuis la barre latérale.")
        return
    
    # Sélection de la feuille à analyser
    selected_sheet = st.selectbox(
        "Sélectionnez une feuille à analyser",
        list(st.session_state.dataframes.keys())
    )
    
    if selected_sheet:
        df = st.session_state.dataframes[selected_sheet]
        create_visualizations(df, selected_sheet)

def show_ai_assistant():
    """Page Assistant IA"""
    st.title("🤖 Assistant IA - Chatbot RAG")
    
    if not st.session_state.dataframes:
        st.info("👆 Veuillez charger les données depuis la barre latérale.")
        return
    
    if not st.session_state.get('openai_api_key'):
        st.warning("⚠️ Veuillez configurer votre clé API OpenAI dans la barre latérale.")
        return
    
    # Initialisation de l'agent
    if 'rag_agent' not in st.session_state:
        with st.spinner("Initialisation de l'agent IA..."):
            st.session_state.rag_agent = initialize_rag_agent(st.session_state.dataframes)
    
    # Affichage de l'historique de chat
    st.subheader("💬 Conversation")
    
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.write(message["content"])
    
    # Zone de saisie
    user_question = st.chat_input("Posez votre question sur les données agricoles...")
    
    if user_question:
        # Ajout de la question à l'historique
        st.session_state.chat_history.append({"role": "user", "content": user_question})
        
        with st.chat_message("user"):
            st.write(user_question)
        
        # Traitement de la question
        with st.chat_message("assistant"):
            with st.spinner("Analyse en cours..."):
                response = chat_with_rag(
                    user_question,
                    st.session_state.rag_agent,
                    st.session_state.dataframes
                )
                st.write(response)
                st.session_state.chat_history.append({"role": "assistant", "content": response})
    
    # Bouton pour réinitialiser la conversation
    if st.button("🗑️ Effacer l'historique"):
        st.session_state.chat_history = []
        st.rerun()

def show_monographie():
    """Page Rapport Monographique"""
    st.title("📚 Rapport Monographique - Province de Chefchaouen")
    
    if not st.session_state.dataframes:
        st.info("👆 Veuillez charger les données depuis la barre latérale.")
        return
    
    if not st.session_state.get('openai_api_key'):
        st.warning("⚠️ Veuillez configurer votre clé API OpenAI dans la barre latérale.")
        return
    
    # Bouton pour générer la monographie
    if st.button("🔄 Générer/Régénérer la monographie", type="primary"):
        with st.spinner("Génération de la monographie en cours... Cela peut prendre quelques minutes."):
            st.session_state.monographie = generate_monographie(st.session_state.dataframes)
    
    # Affichage de la monographie
    if st.session_state.monographie:
        st.markdown(st.session_state.monographie)
        
        # Bouton de téléchargement
        st.download_button(
            label="📥 Télécharger la monographie",
            data=st.session_state.monographie,
            file_name=f"Monographie_Chefchaouen_{datetime.now().strftime('%Y%m%d')}.txt",
            mime="text/plain"
        )
    else:
        st.info("👆 Cliquez sur le bouton ci-dessus pour générer la monographie.")

if __name__ == "__main__":
    main()
