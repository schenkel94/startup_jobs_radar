import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import os

# --- CONFIGURAÇÕES ---
st.set_page_config(page_title="Schenkel JobSearch Greenhouse", page_icon="🕵️", layout="wide")

# Lista de empresas (board tokens do Greenhouse)
# Para adicionar mais, basta descobrir o nome na URL do greenhouse: greenhouse.io/nome-da-empresa
DEFAULT_COMPANIES = [
    # Fintechs e Bancos Digitais (13)
    "nubank",
    "xpinc",
    "picpay",
    "c6bank",
    "inter",
    # "creditasen", # 404
    # "creditas",   # 404 - Provavelmente mudou de ATS
    "btgpactual",
    "pagarme",
    "agibank",
    "bancopan",
    "ebanx",
    "clara",
    "pismo", # Tentar manter, as vezes oscila, mas se der 404 o código novo trata
    
    # Tecnologia e Software (22)
    "ifoodcarreiras", # Corrigido
    "stone",
    "rdstation",
    "vtex",
    "linx",
    "zupinnovation",
    "ilia",
    "zenvia",
    "blip",
    "jusbrasil",
    "wildlifestudios",
    "exactsales",
    "isaac",
    "marketdata",
    "aircompany",
    
    # Proptech (2)
    "quintoandar",
    
    # Educação (2)
    "arcoeducacao",
    
    # Logística e Delivery (4)
    # "deliverymuch", # 404
    # "freterapido",  # 404
    # "open",         # 404
    # "openco",       # 404
    
    # Eventos (1)
    # "sympla",       # 404 - Mudou para Gupy?
    
    # Indústria (1)
    "braskem",
    
    # Agências (3)
    "oliverbrazil",
    
    # Serviços Internacionais (5)
    # "telusdigitalbrazil", # 404
    "hotmartcareersbr",  # Usar: job-boards.eu.greenhouse.io
    
    # Outros (11)
    "flash",
    "getatende",
    "enforce",
    "gympass",
    "99",
    # "meliuz",       # 404 - Gupy
    # "contabilizei", # 404 - Gupy
]

# --- CARREGAR EMPRESAS EXTRAS DO MINERADOR ---
def load_external_companies():
    file_path = "empresas.txt"
    if os.path.exists(file_path):
        with open(file_path, "r") as f:
            # Lê as linhas, remove espaços e ignora vazias
            return [line.strip() for line in f if line.strip()]
    return []

# Junta as empresas padrão com as descobertas pelo minerador e remove duplicatas
external_companies = load_external_companies()
ALL_COMPANIES = sorted(list(set(DEFAULT_COMPANIES + external_companies)))

# Termos obrigatórios (Pelo menos um destes deve aparecer no título)
DEFAULT_KEYWORDS_INCLUDE = [
    "analista de dados",
    "data analyst",
    "analista de bi",
    "bi analyst",
    "business intelligence",
    "analista de negócios",
    "business analyst",
    "dataviz",
    "visualização de dados",
    "analytics",
    "inteligência de mercado"
]

# Termos de exclusão (Se aparecer, a vaga é removida)
DEFAULT_KEYWORDS_EXCLUDE = [
    "engenharia",
    "engineer",
    "ciência de dados",
    "data science",
    "scientist",
    "cientista",
    "estágio", # Opcional: remover se quiser ver estágios
    "banco de talentos" # Opcional: remover vagas genéricas
]

# Termos para identificar trabalho remoto
REMOTE_TERMS = [
    "remoto",
    "remota",
    "homeoffice",
    "home-office",
    "teletrabalho"
]

# --- FUNÇÕES ---

@st.cache_data(ttl=3600) # Cache dos dados por 1 hora para não ficar chamando a API toda hora
def fetch_greenhouse_jobs(board_token):
    """
    Busca vagas na API pública do Greenhouse para uma empresa específica.
    """
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        # A API retorna um dicionário com a chave 'jobs' que é uma lista
        jobs = data.get('jobs', [])
        
        # Adiciona o nome da empresa em cada vaga para identificação posterior
        for job in jobs:
            job['company_slug'] = board_token
            
        return jobs
    except requests.exceptions.HTTPError as e:
        # Se for erro 404 (Não encontrado), apenas ignoramos silenciosamente ou logamos no console
        if e.response.status_code == 404:
            print(f"⚠️ Board não encontrado (404): {board_token}")
            return []
        else:
            st.error(f"Erro de conexão com {board_token}: {e}")
            return []
    except Exception as e:
        st.error(f"Erro ao buscar vagas para {board_token}: {e}")
        return []

def is_relevant_job(title, include_terms, exclude_terms):
    """
    Filtra a vaga baseada no título.
    Retorna True se for relevante, False caso contrário.
    """
    title_lower = title.lower()
    
    # 1. Verifica exclusões primeiro
    for term in exclude_terms:
        if term in title_lower:
            return False
            
    # 2. Verifica inclusões
    for term in include_terms:
        if term in title_lower:
            return True
            
    return False

def check_is_remote(title, location):
    """
    Verifica se a vaga é remota olhando título e localização.
    """
    text_search = (title + " " + location).lower()
    for term in REMOTE_TERMS:
        if term in text_search:
            return True
    return False

def process_jobs(companies_list, include_terms, exclude_terms, only_remote):
    """
    Itera sobre as empresas, busca e filtra as vagas.
    """
    all_relevant_jobs = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, company in enumerate(companies_list):
        company = company.strip() # Remove espaços extras
        if not company: continue

        status_text.text(f"Buscando vagas em: {company}...")
        raw_jobs = fetch_greenhouse_jobs(company)
        
        for job in raw_jobs:
            if is_relevant_job(job['title'], include_terms, exclude_terms):
                
                loc_name = job['location']['name'] if 'location' in job else "Não informado"
                is_remote = check_is_remote(job['title'], loc_name)

                if only_remote and not is_remote:
                    continue

                # Simplificando o objeto para o DataFrame
                clean_job = {
                    "Empresa": company,
                    "Título": job['title'],
                    "Localização": loc_name,
                    "Remoto?": "✅ Sim" if is_remote else "❌ Não",
                    "Atualizado em": datetime.strptime(job['updated_at'], "%Y-%m-%dT%H:%M:%S%z").strftime("%d/%m/%Y"),
                    "Link": job['absolute_url']
                }
                all_relevant_jobs.append(clean_job)
        
        progress_bar.progress((i + 1) / len(companies_list))
        
    status_text.empty()
    progress_bar.empty()
    
    return all_relevant_jobs

# --- SIDEBAR (CONFIGURAÇÃO) ---
with st.sidebar:
    st.header("⚙️ Configurações")
    
    # Input de Empresas
    selected_companies = st.multiselect(
        "Empresas (Selecione)",
        options=ALL_COMPANIES,
        default=ALL_COMPANIES
    )
    
    # Inputs de Palavras-Chave
    st.subheader("Filtros de Palavras")
    include_input = st.text_area("Termos Obrigatórios (Inclusão)", value=", ".join(DEFAULT_KEYWORDS_INCLUDE))
    exclude_input = st.text_area("Termos Proibidos (Exclusão)", value=", ".join(DEFAULT_KEYWORDS_EXCLUDE))
    
    selected_include = [t.strip().lower() for t in include_input.split(',')]
    selected_exclude = [t.strip().lower() for t in exclude_input.split(',')]

    # Filtro Remoto
    st.subheader("Preferências")
    filter_remote = st.toggle("🏠 Apenas Vagas Remotas", value=False)

# --- INTERFACE (STREAMLIT) ---

st.title("🕵️ Schenkel JobSearch Greenhouse")
st.markdown(
    """
    Este app busca automaticamente vagas focadas em **Análise de Dados, BI e Negócios** 
    nas empresas listadas, filtrando fora Engenharia e Ciência de Dados.
    """
)

# Botão para atualizar
if st.button("Buscar Vagas Agora"):
    with st.spinner('Varrendo APIs do Greenhouse...'):
        results = process_jobs(selected_companies, selected_include, selected_exclude, filter_remote)
        
    if results:
        df = pd.DataFrame(results)
        
        st.success(f"Encontradas {len(df)} vagas relevantes!")
        
        # Exibição em Tabela Interativa
        st.dataframe(
            df,
            column_config={
                "Link": st.column_config.LinkColumn("Candidatura", display_text="🔗 Aplicar"),
                "Remoto?": st.column_config.TextColumn("Remoto?", width="small")
            },
            hide_index=True,
            use_container_width=True
        )
        
        # Exibição alternativa em Cards (opcional, visualmente agradável)
        st.markdown("---")
        st.subheader("Detalhes das Vagas")
        for _, row in df.iterrows():
            remote_icon = "🏠" if "Sim" in row['Remoto?'] else "🏢"
            with st.expander(f"{remote_icon} {row['Empresa'].upper()} - {row['Título']}"):
                st.write(f"**Local:** {row['Localização']}")
                st.write(f"**Remoto:** {row['Remoto?']}")
                st.write(f"**Data:** {row['Atualizado em']}")
                st.markdown(f"[👉 Clique para aplicar]({row['Link']})")
                
    else:
        st.warning("Nenhuma vaga encontrada com os filtros atuais nas empresas listadas.")
