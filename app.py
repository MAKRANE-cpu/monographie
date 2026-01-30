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
    .answer-box {
        background-color: #e8f5e9;
        border-radius: 10px;
        padding: 20px;
        margin: 20px 0;
        border-left: 5px solid #4caf50;
    }
    .warning-box {
        background-color: #fff3e0;
        border-radius: 10px;
        padding: 20px;
        margin: 20px 0;
        border-left: 5px solid #ff9800;
    }
    .info-box {
        background-color: #e3f2fd;
        border-radius: 10px;
        padding: 20px;
        margin: 20px 0;
        border-left: 5px solid #2196f3;
    }
    .stButton>button {
        background-color: #2E8B57;
        color: white;
        font-weight: 600;
        border: none;
        padding: 10px 24px;
        border-radius: 8px;
    }
    .stButton>button:hover {
        background-color: #3CB371;
    }
</style>
""", unsafe_allow_html=True)

# --- FONCTIONS UTILITAIRES ---
def clean_val(val):
    """Nettoyage des valeurs numériques"""
    if pd.isna(val) or val in ["", None]:
        return 0.0
    s = str(val).strip()
    s = re.sub(r'[\s\xa0,]+', '', s)
    match = re.search(r"[-+]?\d*\.?\d+", s)
    return float(match.group()) if match else 0.0

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
        
        creds = Credentials.from_service_account_info(
            st.secrets["gcp_service_account"], 
            scopes=scope
        )
        
        client = gspread.authorize(creds)
        sh = client.open_by_key(SHEET_ID)
        
        all_data = {}
        
        for ws in sh.worksheets():
            try:
                raw = ws.get_all_values()
                
                if not raw:
                    continue
                
                # Chercher "Commune"
                header_idx = None
                for i, row in enumerate(raw[:10]):
                    row_lower = [str(cell).lower().strip() for cell in row]
                    if "commune" in row_lower:
                        header_idx = i
                        break
                
                if header_idx is None:
                    continue
                
                # En-têtes
                headers = raw[header_idx:header_idx+2]
                
                # Noms de colonnes
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
                
                # Données
                data_start = header_idx + 2
                data_rows = raw[data_start:] if data_start < len(raw) else []
                
                # DataFrame
                df = pd.DataFrame(data_rows, columns=col_names)
                
                # Nettoyage
                for col in df.columns:
                    if 'commune' not in col.lower():
                        df[col] = df[col].apply(clean_val)
                
                # Colonne Commune
                if 'Commune' in df.columns:
                    df['Commune'] = df['Commune'].astype(str).str.strip()
                    df = df[~df['Commune'].str.contains('total|TOTAL|S/T|munici', case=False, na=False)]
                    df = df[df['Commune'] != '']
                
                all_data[ws.title] = df
                
            except Exception as e:
                continue
        
        return all_data
        
    except Exception as e:
        st.error(f"Erreur de chargement : {str(e)}")
        return {}

# --- FONCTION D'ANALYSE GEMINI ---
def analyze_with_gemini(question, data_dict, model):
    """Utilise Gemini pour analyser la question avec les données"""
    try:
        # Préparer un échantillon des données pour le contexte
        context_data = "DONNÉES AGRICOLES DE CHEFCHAOUEN (échantillon):\n\n"
        
        # Ajouter des données clés pour le contexte
        for sheet_name, df in list(data_dict.items())[:8]:  # Limiter à 8 feuilles
            # Prendre un échantillon de 5 lignes
            sample = df.head(3)
            
            # Convertir en format texte lisible
            sample_text = sample.to_string(index=False)
            
            context_data += f"=== {sheet_name} ===\n"
            context_data += f"Colonnes: {', '.join(df.columns[:5])}...\n"
            context_data += f"Échantillon:\n{sample_text}\n\n"
        
        # Ajouter des informations sur les communes disponibles
        communes = set()
        for df in data_dict.values():
            if 'Commune' in df.columns:
                communes.update(df['Commune'].unique())
        
        context_data += f"\n=== COMMUNES DISPONIBLES ===\n"
        context_data += f"{', '.join(sorted(list(communes))[:15])}...\n"
        
        # Préparer le prompt pour Gemini
        prompt = f"""
        Tu es un expert agronome spécialiste de la province de Chefchaouen au Maroc.
        Tu as accès aux données agricoles complètes de la province.
        
        CONTEXTE DES DONNÉES:
        {context_data[:4000]}
        
        INSTRUCTIONS IMPORTANTES:
        1. Analyse la question de l'utilisateur
        2. Cherche dans les données disponibles
        3. Donne une réponse PRÉCISE et CONCRÈTE
        4. Mentionne des CHIFFRES EXACTS quand c'est possible
        5. Cite des NOMS DE COMMUNES spécifiques
        6. Propose des RECOMMANDATIONS pratiques
        7. Structure ta réponse avec des titres clairs
        8. Si tu ne trouves pas la réponse exacte, fais une analyse logique
        
        QUESTION DE L'UTILISATEUR: {question}
        
        RÉPONSE (en français, format professionnel):
        """
        
        # Appeler Gemini
        response = model.generate_content(prompt)
        
        return response.text
        
    except Exception as e:
        return f"""
        <div class='warning-box'>
        <h3>⚠️ Erreur d'analyse Gemini</h3>
        <p>Erreur: {str(e)}</p>
        <p>Je vais tenter une analyse manuelle des données...</p>
        </div>
        """

def analyze_question_manually(question, data_dict):
    """Analyse manuelle de la question en cas d'échec de Gemini"""
    question_lower = question.lower()
    
    # Détecter la culture demandée
    crops = {
        'tomate': ['tomate', 'tomates'],
        'pomme de terre': ['pomme de terre', 'patate', 'pdt'],
        'carotte': ['carotte', 'carottes'],
        'oignon': ['oignon', 'oignons'],
        'ail': ['ail'],
        'blé': ['blé', 'ble'],
        'orge': ['orge'],
        'maïs': ['maïs', 'mais'],
        'olivier': ['olivier', 'olive'],
        'figuier': ['figuier', 'figue']
    }
    
    detected_crop = None
    for crop, keywords in crops.items():
        if any(keyword in question_lower for keyword in keywords):
            detected_crop = crop
            break
    
    if detected_crop:
        # Chercher les données pour cette culture
        results = []
        
        for sheet_name, df in data_dict.items():
            for col in df.columns:
                col_lower = str(col).lower()
                
                # Chercher la culture dans le nom de colonne
                crop_found = False
                for keyword in crops[detected_crop]:
                    if keyword in col_lower:
                        crop_found = True
                        break
                
                if crop_found:
                    # Vérifier si c'est une colonne de surface
                    if any(word in col_lower for word in ['sup', 'surface', 'ha']):
                        for _, row in df.iterrows():
                            commune = row.get('Commune', 'Inconnue')
                            value = row[col]
                            if pd.notna(value) and value > 0:
                                results.append({
                                    'commune': commune,
                                    'valeur': value,
                                    'feuille': sheet_name,
                                    'colonne': col
                                })
        
        if results:
            # Trouver la plus grande valeur
            df_results = pd.DataFrame(results)
            max_row = df_results.loc[df_results['valeur'].idxmax()]
            
            return f"""
            <div class='answer-box'>
            <h3>📊 Analyse pour: "{question}"</h3>
            
            <h4>🥇 Résultat:</h4>
            <div style='background-color: white; padding: 15px; border-radius: 8px; margin: 10px 0;'>
            <h2 style='color: #2E8B57; margin: 0;'>{max_row['commune']}</h2>
            <p style='font-size: 1.2em; margin: 5px 0;'>avec <strong>{max_row['valeur']} hectares</strong> de {detected_crop}s</p>
            <p style='color: #666; font-size: 0.9em;'>Source: {max_row['feuille']} - {max_row['colonne']}</p>
            </div>
            
            <h4>📈 Top 5 des communes:</h4>
            <table style='width: 100%; border-collapse: collapse;'>
            <tr style='background-color: #2E8B57; color: white;'>
                <th style='padding: 10px; text-align: left;'>Rang</th>
                <th style='padding: 10px; text-align: left;'>Commune</th>
                <th style='padding: 10px; text-align: left;'>Superficie (ha)</th>
            </tr>
            """
            
            top_5 = df_results.nlargest(5, 'valeur')
            for i, (_, row) in enumerate(top_5.iterrows(), 1):
                response += f"""
                <tr style='border-bottom: 1px solid #ddd;'>
                    <td style='padding: 10px;'>{i}</td>
                    <td style='padding: 10px; font-weight: bold;'>{row['commune']}</td>
                    <td style='padding: 10px;'>{row['valeur']} ha</td>
                </tr>
                """
            
            response += f"""
            </table>
            
            <h4>🎯 Recommandations:</h4>
            <p>Pour développer la culture des {detected_crop}s, concentrez-vous d'abord sur <strong>{max_row['commune']}</strong> 
            où l'expérience existe déjà ({max_row['valeur']} ha). Ensuite, étendez aux autres communes du classement.</p>
            </div>
            """
            
            return response
    
    # Réponse générale si rien n'est trouvé
    return f"""
    <div class='info-box'>
    <h3>🔍 Analyse de votre question</h3>
    
    <p>Question: <strong>"{question}"</strong></p>
    
    <h4>📋 Données disponibles:</h4>
    <p>Je dispose de {len(data_dict)} feuilles de données agricoles pour Chefchaouen.</p>
    
    <h4>🎯 Pour une meilleure réponse:</h4>
    <ul>
        <li>Assurez-vous que la culture est bien présente dans les données</li>
        <li>Vérifiez l'orthographe (ex: "tomate" au lieu de "thomate")</li>
        <li>Consultez la page "📋 Données" pour voir les feuilles disponibles</li>
    </ul>
    
    <h4>🌱 Cultures couramment analysées:</h4>
    <div style='display: flex; flex-wrap: wrap; gap: 10px; margin: 10px 0;'>
        <div style='background-color: #4caf50; color: white; padding: 5px 10px; border-radius: 5px;'>Tomates</div>
        <div style='background-color: #4caf50; color: white; padding: 5px 10px; border-radius: 5px;'>Pommes de terre</div>
        <div style='background-color: #4caf50; color: white; padding: 5px 10px; border-radius: 5px;'>Carottes</div>
        <div style='background-color: #4caf50; color: white; padding: 5px 10px; border-radius: 5px;'>Blé</div>
        <div style='background-color: #4caf50; color: white; padding: 5px 10px; border-radius: 5px;'>Oliviers</div>
    </div>
    </div>
    """

# --- INITIALISATION ---
if 'page' not in st.session_state:
    st.session_state.page = "Accueil"
if 'chat_history' not in st.session_state:
    st.session_state.chat_history = []
if 'gemini_model' not in st.session_state:
    st.session_state.gemini_model = None

# Chargement des données
with st.spinner("🔄 Chargement des données agricoles..."):
    data_dict = load_data()
    
    if not data_dict:
        st.error("❌ Impossible de charger les données.")
        st.stop()
    
    st.success(f"✅ {len(data_dict)} feuilles chargées!")

# Initialisation Gemini
if "gemini_api_key" in st.secrets:
    try:
        genai.configure(api_key=st.secrets["gemini_api_key"])
        # Essayer différents modèles
        try:
            model = genai.GenerativeModel('gemini-pro')
        except:
            try:
                model = genai.GenerativeModel('models/gemini-pro')
            except:
                # Dernier recours: utiliser gemini-1.0-pro
                model = genai.GenerativeModel('gemini-1.0-pro')
        
        st.session_state.gemini_model = model
    except Exception as e:
        st.warning(f"⚠️ Gemini non disponible: {str(e)}")
        st.session_state.gemini_model = None
else:
    st.info("ℹ️ Pour des analyses avancées, ajoutez une clé API Gemini dans les secrets")
    st.session_state.gemini_model = None

# --- SIDEBAR ---
with st.sidebar:
    st.markdown('<div class="main-header">🌿 Navigation</div>', unsafe_allow_html=True)
    
    # Navigation
    if st.button("🏠 Accueil", use_container_width=True, type="primary"):
        st.session_state.page = "Accueil"
        st.rerun()
    
    if st.button("🤖 Assistant IA", use_container_width=True):
        st.session_state.page = "Assistant"
        st.rerun()
    
    if st.button("📊 Visualisations", use_container_width=True):
        st.session_state.page = "Viz"
        st.rerun()
    
    if st.button("📋 Exploration Données", use_container_width=True):
        st.session_state.page = "Donnees"
        st.rerun()
    
    st.divider()
    
    # Stats
    if data_dict:
        total_rows = sum(len(df) for df in data_dict.values())
        total_communes = set()
        for df in data_dict.values():
            if 'Commune' in df.columns:
                total_communes.update(df['Commune'].unique())
        
        st.metric("Feuilles", len(data_dict))
        st.metric("Communes", len(total_communes))
        st.metric("Lignes", f"{total_rows:,}")
    
    st.divider()
    
    # Statut Gemini
    if st.session_state.gemini_model:
        st.success("✅ Gemini Actif")
    else:
        st.warning("⚠️ Gemini Inactif")
    
    st.divider()
    
    if st.button("🔄 Actualiser", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

# --- PAGE ACCUEIL ---
if st.session_state.page == "Accueil":
    st.markdown('<div class="main-header">🌱 Agri-Analytics Chefchaouen</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown("""
        ### 📊 Système d'Analyse Agricole avec IA
        
        **🎯 Posez vos questions en français naturel:**
        - "Quelle commune a la plus grande superficie de tomates?"
        - "Où sont les meilleurs rendements en blé?"
        - "Quelles communes cultivent des pommes de terre?"
        - "Comparer Bab Taza et Tanaqob pour l'irrigation"
        - "Quelle est la superficie totale de carottes?"
        
        **🤖 Fonctionnalités:**
        - 🔍 **Analyse IA** avec Google Gemini
        - 📈 **Réponses précises** basées sur vos données
        - 🏆 **Classements automatiques** des communes
        - 💡 **Recommandations** personnalisées
        
        **📋 Données analysées:**
        - Monographie agricole complète de Chefchaouen
        - 27+ communes analysées
        - Superficies, rendements, productions
        - Données d'irrigation et pédologiques
        """)
    
    with col2:
        st.markdown('<div style="background-color: #f8f9fa; padding: 20px; border-radius: 10px;">', unsafe_allow_html=True)
        st.markdown("### 🚀 Questions rapides")
        
        if st.button("🍅 Superficie tomates", use_container_width=True):
            st.session_state.page = "Assistant"
            st.session_state.quick_question = "Quelle commune a la plus grande superficie de tomates?"
            st.rerun()
        
        if st.button("🥔 Pommes de terre", use_container_width=True):
            st.session_state.page = "Assistant"
            st.session_state.quick_question = "Quelle commune a la plus grande superficie de pommes de terre?"
            st.rerun()
        
        if st.button("🥕 Carottes", use_container_width=True):
            st.session_state.page = "Assistant"
            st.session_state.quick_question = "Quelle commune a la plus grande superficie de carottes?"
            st.rerun()
        
        if st.button("🌾 Rendement blé", use_container_width=True):
            st.session_state.page = "Assistant"
            st.session_state.quick_question = "Quelle commune a le meilleur rendement en blé?"
            st.rerun()
        
        if st.button("💧 Irrigation", use_container_width=True):
            st.session_state.page = "Assistant"
            st.session_state.quick_question = "Quelles communes ont le plus d'irrigation?"
            st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Aperçu
    st.divider()
    st.markdown("### 📋 Feuilles de données disponibles")
    
    cols = st.columns(3)
    sheet_list = list(data_dict.keys())
    
    for i, sheet_name in enumerate(sheet_list[:6]):
        with cols[i % 3]:
            with st.expander(f"📄 {sheet_name[:25]}..."):
                df = data_dict[sheet_name]
                st.write(f"**{len(df)}** lignes")
                st.write(f"**{len(df.columns)}** colonnes")
                if 'Commune' in df.columns:
                    st.write(f"**{df['Commune'].nunique()}** communes")
                st.dataframe(df.head(3), use_container_width=True, height=150)

# --- PAGE ASSISTANT IA ---
elif st.session_state.page == "Assistant":
    st.markdown('<div class="main-header">🤖 Assistant Agricole IA</div>', unsafe_allow_html=True)
    
    st.markdown("""
    ### 💬 Posez votre question sur l'agriculture à Chefchaouen
    
    **L'IA analysera vos données et répondra précisément:**
    """)
    
    # Saisie de la question
    col1, col2 = st.columns([3, 1])
    
    with col1:
        user_question = st.text_input(
            "Votre question:",
            placeholder="Ex: Quelle commune a la plus grande superficie de carottes?",
            key="question_input"
        )
    
    with col2:
        analyze_btn = st.button("🔍 Analyser", use_container_width=True, type="primary")
    
    # Question rapide
    if 'quick_question' in st.session_state:
        user_question = st.session_state.quick_question
        del st.session_state.quick_question
        analyze_btn = True
    
    # Traitement de la question
    if analyze_btn and user_question:
        # Ajouter à l'historique
        st.session_state.chat_history.append({
            "role": "user",
            "content": user_question,
            "time": datetime.now().strftime("%H:%M")
        })
        
        # Analyser avec l'IA
        with st.spinner("🔍 L'IA analyse vos données..."):
            try:
                if st.session_state.gemini_model:
                    # Utiliser Gemini
                    response = analyze_with_gemini(
                        user_question, 
                        data_dict, 
                        st.session_state.gemini_model
                    )
                else:
                    # Analyse manuelle
                    response = analyze_question_manually(user_question, data_dict)
                
            except Exception as e:
                response = f"""
                <div class='warning-box'>
                <h3>⚠️ Erreur lors de l'analyse</h3>
                <p>Une erreur est survenue: {str(e)}</p>
                <p>Veuillez réessayer avec une question différente.</p>
                </div>
                """
        
        # Ajouter la réponse à l'historique
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": response,
            "time": datetime.now().strftime("%H:%M")
        })
    
    # Afficher l'historique
    st.markdown("---")
    st.markdown("### 📝 Historique des analyses")
    
    if not st.session_state.chat_history:
        st.info("👆 Posez votre première question ci-dessus pour commencer!")
    else:
        for message in reversed(st.session_state.chat_history[-3:]):
            with st.container():
                if message["role"] == "user":
                    st.markdown(f"""
                    <div style='background-color: #e3f2fd; padding: 15px; border-radius: 10px; margin: 10px 0;'>
                    <strong>👤 Vous ({message['time']}):</strong><br>
                    {message['content']}
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.markdown(message['content'], unsafe_allow_html=True)
    
    # Configuration Gemini
    st.markdown("---")
    with st.expander("⚙️ Configuration Gemini"):
        if st.session_state.gemini_model:
            st.success("✅ Gemini est correctement configuré")
        else:
            st.warning("""
            ⚠️ Gemini n'est pas configuré
            
            Pour activer l'analyse IA avancée, ajoutez dans `.streamlit/secrets.toml`:
            
            ```toml
            gemini_api_key = "votre_cle_api_ici"
            ```
            
            **Pour obtenir une clé API:**
            1. Allez sur [Google AI Studio](https://makersuite.google.com/app/apikey)
            2. Créez un compte Google (gratuit)
            3. Générez une clé API
            4. Ajoutez-la aux secrets
            5. Redémarrez l'application
            """)
    
    # Bouton retour
    st.markdown("---")
    if st.button("← Retour à l'accueil", use_container_width=True):
        st.session_state.page = "Accueil"
        st.rerun()

# --- PAGE VISUALISATIONS ---
elif st.session_state.page == "Viz":
    st.markdown('<div class="main-header">📊 Visualisations Interactives</div>', unsafe_allow_html=True)
    
    if not data_dict:
        st.warning("Aucune donnée disponible")
        st.stop()
    
    # Sélection de la feuille
    selected_sheet = st.selectbox(
        "Sélectionnez une feuille de données:",
        list(data_dict.keys())
    )
    
    if selected_sheet:
        df = data_dict[selected_sheet]
        
        # Vérifier les colonnes disponibles
        if 'Commune' not in df.columns:
            st.warning("Cette feuille ne contient pas de colonne 'Commune'")
            st.dataframe(df, use_container_width=True)
        else:
            # Colonnes numériques
            numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
            
            if numeric_cols:
                col1, col2 = st.columns([1, 3])
                
                with col1:
                    selected_col = st.selectbox(
                        "Sélectionnez une variable:",
                        numeric_cols
                    )
                    
                    chart_type = st.selectbox(
                        "Type de graphique:",
                        ["Barres verticales", "Barres horizontales", "Camembert"]
                    )
                    
                    top_n = st.slider(
                        "Nombre de communes à afficher:",
                        5, 30, 15
                    )
                
                with col2:
                    # Préparer les données
                    plot_data = df[['Commune', selected_col]].copy()
                    plot_data = plot_data.dropna()
                    plot_data = plot_data.sort_values(selected_col, ascending=False).head(top_n)
                    
                    # Créer le graphique
                    if chart_type == "Barres verticales":
                        fig = px.bar(
                            plot_data,
                            x='Commune',
                            y=selected_col,
                            title=f"{selected_col} par commune",
                            color=selected_col,
                            color_continuous_scale="greens"
                        )
                        fig.update_layout(xaxis_tickangle=-45)
                    
                    elif chart_type == "Barres horizontales":
                        fig = px.bar(
                            plot_data,
                            y='Commune',
                            x=selected_col,
                            title=f"{selected_col} par commune",
                            color=selected_col,
                            color_continuous_scale="greens",
                            orientation='h'
                        )
                    
                    else:  # Camembert
                        fig = px.pie(
                            plot_data,
                            values=selected_col,
                            names='Commune',
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
            else:
                st.info("Cette feuille ne contient pas de colonnes numériques")
                st.dataframe(df, use_container_width=True)
    
    # Bouton retour
    st.markdown("---")
    if st.button("← Retour à l'accueil", use_container_width=True):
        st.session_state.page = "Accueil"
        st.rerun()

# --- PAGE DONNÉES ---
else:
    st.markdown('<div class="main-header">📋 Exploration des Données</div>', unsafe_allow_html=True)
    
    if not data_dict:
        st.warning("Aucune donnée disponible")
        st.stop()
    
    # Sélection de la feuille
    selected_sheet = st.selectbox(
        "Sélectionnez une feuille à explorer:",
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
        
        tab1, tab2 = st.tabs(["Aperçu", "Statistiques"])
        
        with tab1:
            # Options d'affichage
            rows_to_show = st.slider(
                "Nombre de lignes à afficher:",
                10, 100, 20
            )
            
            st.dataframe(df.head(rows_to_show), use_container_width=True)
        
        with tab2:
            # Statistiques descriptives
            numeric_df = df.select_dtypes(include=[np.number])
            
            if not numeric_df.empty:
                st.dataframe(numeric_df.describe(), use_container_width=True)
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
    
    # Bouton retour
    st.markdown("---")
    if st.button("← Retour à l'accueil", use_container_width=True):
        st.session_state.page = "Accueil"
        st.rerun()

# --- FOOTER ---
st.divider()
st.caption(f"🌿 Agri-Analytics Chefchaouen • Données: {len(data_dict)} feuilles • {datetime.now().strftime('%Y-%m-%d %H:%M')}")