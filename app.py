from datetime import datetime
from typing import Any

import pandas as pd
import requests
import streamlit as st


st.set_page_config(
    page_title="SQL IDE + AI Assistant",
    page_icon="🧠",
    layout="wide",
)


DEFAULT_SQL = """SELECT id, customer_name, total_value, created_at
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;"""


def resolve_api_base_url() -> str:
    try:
        if "api" in st.secrets and "base_url" in st.secrets["api"]:
            return str(st.secrets["api"]["base_url"]).rstrip("/")
        if "API_BASE_URL" in st.secrets:
            return str(st.secrets["API_BASE_URL"]).rstrip("/")
    except Exception:
        pass
    return "http://localhost:8080"


API_BASE_URL = resolve_api_base_url()


def init_state() -> None:
    if "sql_text" not in st.session_state:
        st.session_state.sql_text = DEFAULT_SQL
    if "assistant_messages" not in st.session_state:
        st.session_state.assistant_messages = [
            {
                "role": "assistant",
                "content": "Descreva o que você quer consultar e eu te ajudo a montar o SQL.",
            }
        ]
    if "last_result" not in st.session_state:
        st.session_state.last_result = None
    if "last_error" not in st.session_state:
        st.session_state.last_error = None
    if "last_raw_response" not in st.session_state:
        st.session_state.last_raw_response = None
    if "query_history" not in st.session_state:
        st.session_state.query_history = []
    if "favorite_queries" not in st.session_state:
        st.session_state.favorite_queries = []
    if "favorite_name" not in st.session_state:
        st.session_state.favorite_name = ""
    if "assistant_pending_prompt" not in st.session_state:
        st.session_state.assistant_pending_prompt = None
    if "assistant_pending_sql" not in st.session_state:
        st.session_state.assistant_pending_sql = None


def call_sql_api(sql_text: str) -> tuple[Any, Any, str | None]:
    url = f"{API_BASE_URL.rstrip('/')}/sql/run"
    try:
        response = requests.post(url, json={"sql": sql_text}, timeout=30)
        payload = response.json()

        # Contrato atual do backend: ApiResponse { success, data, error, meta }
        if isinstance(payload, dict) and "success" in payload:
            if payload.get("success") is True:
                return payload.get("data"), payload, None

            error = payload.get("error") or {}
            message = error.get("message") or "Erro retornado pela API SQL."
            code = error.get("code")
            detail = f"{code}: {message}" if code else message
            return None, payload, detail

        # Fallback para contrato legado (payload direto)
        response.raise_for_status()
        return payload, payload, None
    except ValueError:
        return None, None, f"Falha ao interpretar resposta JSON da API SQL ({url})."
    except requests.RequestException as exc:
        return None, None, f"Falha ao chamar API SQL ({url}): {exc}"


def call_assistant_api(prompt: str, current_sql: str) -> tuple[str | None, dict[str, Any] | None, str | None]:
    url = f"{API_BASE_URL.rstrip('/')}/assistant/suggest"
    try:
        response = requests.post(
            url,
            json={"prompt": prompt, "currentSql": current_sql},
            timeout=30,
        )
        payload = response.json()

        if isinstance(payload, dict) and "success" in payload:
            if payload.get("success") is True:
                data = payload.get("data") or {}
                suggestion = data.get("suggestion")
                if not suggestion:
                    suggestion = "A API respondeu sem sugestão de SQL."
                metadata_context = data.get("metadataContext")
                return suggestion, metadata_context, None

            error = payload.get("error") or {}
            message = error.get("message") or "Erro retornado pela API do assistente."
            code = error.get("code")
            detail = f"{code}: {message}" if code else message
            return None, None, detail

        # Fallback legado
        response.raise_for_status()
        suggestion = payload.get("suggestion") or payload.get("sql")
        if not suggestion:
            suggestion = "A API respondeu, mas não retornou `suggestion` nem `sql`."
        return suggestion, None, None
    except ValueError:
        return None, None, f"Falha ao interpretar resposta JSON da API do assistente ({url})."
    except requests.RequestException as exc:
        return None, None, f"Falha ao chamar API do assistente ({url}): {exc}"


def normalize_to_dataframe(payload: Any) -> pd.DataFrame:
    if isinstance(payload, list):
        if len(payload) == 0:
            return pd.DataFrame()
        if isinstance(payload[0], dict):
            return pd.DataFrame(payload)
        return pd.DataFrame({"result": payload})

    if isinstance(payload, dict):
        # Contrato SQL atual retorna rows/columns em data
        if "data" in payload and isinstance(payload["data"], list):
            return pd.DataFrame(payload["data"])
        if "rows" in payload and isinstance(payload["rows"], list):
            rows = payload["rows"]
            columns = payload.get("columns")
            if columns and isinstance(columns, list):
                return pd.DataFrame(rows, columns=columns)
            return pd.DataFrame(rows)
        return pd.json_normalize(payload)

    return pd.DataFrame({"result": [payload]})


def sql_preview(sql_text: str, max_len: int = 70) -> str:
    one_line = " ".join(sql_text.split())
    if len(one_line) <= max_len:
        return one_line
    return f"{one_line[:max_len].rstrip()}..."


def add_to_history(sql_text: str, success: bool, result_df: pd.DataFrame | None, error: str | None) -> None:
    row_count = 0
    if result_df is not None:
        row_count = len(result_df.index)
    st.session_state.query_history.insert(
        0,
        {
            "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            "sql": sql_text,
            "preview": sql_preview(sql_text),
            "success": success,
            "rows": row_count,
            "error": error,
        },
    )
    st.session_state.query_history = st.session_state.query_history[:25]


def apply_styles() -> None:
    st.markdown(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=Space+Grotesk:wght@500;700&display=swap');

            .stApp {
                font-family: "DM Sans", sans-serif;
                background:
                    radial-gradient(circle at 15% 18%, rgba(38, 198, 218, 0.13), transparent 42%),
                    radial-gradient(circle at 86% 12%, rgba(245, 166, 35, 0.12), transparent 38%),
                    linear-gradient(160deg, #edf4fb 0%, #f8f5ec 100%);
            }
            [data-testid="stAppViewContainer"] > .main {
                padding-top: 1.2rem;
            }
            [data-testid="stMainBlockContainer"] {
                max-width: none;
                padding-left: 1rem;
                padding-right: 1rem;
            }
            [data-testid="stHeader"] {
                background: rgba(255, 255, 255, 0.35);
                backdrop-filter: blur(8px);
            }
            .main-title {
                font-family: "Space Grotesk", sans-serif;
                font-size: 2.1rem;
                font-weight: 700;
                letter-spacing: -0.7px;
                margin-bottom: 0.3rem;
                color: #102a43;
            }
            .main-subtitle {
                color: #486581;
                margin-bottom: 0.75rem;
                font-size: 1.03rem;
            }
            .api-pill {
                display: inline-block;
                padding: 0.38rem 0.75rem;
                border-radius: 999px;
                border: 1px solid #bfd6ea;
                background: rgba(255, 255, 255, 0.78);
                color: #1f3a56;
                font-size: 0.85rem;
                margin-bottom: 0.7rem;
            }
            .card-title {
                font-family: "Space Grotesk", sans-serif;
                color: #102a43;
                font-weight: 700;
                font-size: 1.25rem;
                letter-spacing: -0.3px;
                margin-bottom: 0.24rem;
            }
            .card-caption {
                color: #627d98;
                font-size: 0.95rem;
                margin-bottom: 1.05rem;
            }
            div[data-testid="stVerticalBlockBorderWrapper"] {
                background: rgba(255, 255, 255, 0.72);
                border: 1px solid #bfd1e3;
                border-radius: 16px;
                box-shadow: 0 8px 22px rgba(16, 42, 67, 0.08);
                overflow: hidden;
            }
            div[data-testid="stVerticalBlockBorderWrapper"] > div[data-testid="stVerticalBlock"] {
                padding: 1.05rem 1.1rem 1.15rem 1.1rem;
            }
            .section-gap {
                height: 0.45rem;
            }
            .chip {
                display: inline-block;
                padding: 5px 11px;
                border-radius: 999px;
                background: #e9f3ff;
                border: 1px solid #bfd6ea;
                color: #1b3e5d;
                font-size: 0.78rem;
                margin-bottom: 0.6rem;
            }
            .history-meta {
                color: #486581;
                font-size: 0.93rem;
                margin: 0.25rem 0 0.55rem 0;
            }
            .history-ok {
                color: #0f8f46;
                font-weight: 700;
            }
            .history-err {
                color: #c92a2a;
                font-weight: 700;
            }
            div[data-testid="stCodeBlock"] {
                border-radius: 12px;
                border: 1px solid #d7e2ee;
            }
            .stButton > button {
                border-radius: 12px;
                height: 2.45rem;
                font-weight: 600;
            }
            .stTextInput, .stTextArea {
                margin-bottom: 0.25rem;
            }
            .stButton {
                margin-top: 0.2rem;
            }
            .stTextInput input, .stTextArea textarea {
                border-radius: 12px;
            }
            .stDataFrame {
                border-radius: 12px;
                overflow: hidden;
            }
            [data-testid="stChatMessage"] {
                margin-bottom: 0.82rem;
                padding: 0.78rem 0.9rem;
                border: 1px solid #c8d9ea;
                border-radius: 14px;
                background: #f5f9ff;
                align-items: flex-start !important;
            }
            [data-testid="stChatMessageContent"] {
                border: none !important;
                box-shadow: none !important;
                background: transparent !important;
                padding: 0 !important;
                width: 100% !important;
                min-height: auto !important;
                height: auto !important;
                overflow: visible !important;
            }
            [data-testid="stChatMessageContent"] > div {
                border: none !important;
                box-shadow: none !important;
                background: transparent !important;
                padding: 0 !important;
                border-radius: 0 !important;
                min-height: auto !important;
                height: auto !important;
                overflow: visible !important;
            }
            [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p {
                line-height: 1.58;
                margin: 0.2rem 0;
            }
            [data-testid="stChatInput"] {
                margin-top: 0.3rem;
                margin-bottom: 0.2rem;
            }
            [data-testid="stChatInput"] textarea {
                border-radius: 12px !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    st.markdown('<div class="main-title">SQL Studio + AI Assistant</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="main-subtitle">Interface pronta para conectar no backend e executar consultas SQL com apoio de IA.</div>',
        unsafe_allow_html=True,
    )
    st.markdown(f'<div class="api-pill">API local: <code>{API_BASE_URL}</code></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-gap"></div>', unsafe_allow_html=True)


def render_sql_editor() -> None:
    with st.container(border=True):
        st.markdown('<div class="card-title">Editor SQL</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="card-caption">Escreva sua query e clique em Run. O backend fará todo o processamento.</div>',
            unsafe_allow_html=True,
        )

        st.session_state.sql_text = st.text_area(
            "Query SQL",
            value=st.session_state.sql_text,
            height=290,
            label_visibility="collapsed",
        )

        st.session_state.favorite_name = st.text_input(
            "Nome da consulta favorita (opcional)",
            value=st.session_state.favorite_name,
            placeholder="Ex.: Top clientes do mês",
        )

        col_run, col_save = st.columns(2, gap="medium")
        with col_run:
            run_button = st.button("Run Query", type="primary", use_container_width=True)
        with col_save:
            save_button = st.button("Salvar consulta", use_container_width=True)

        if save_button:
            favorite_name = st.session_state.favorite_name.strip()
            if not favorite_name:
                favorite_name = f"Consulta {datetime.now().strftime('%H:%M:%S')}"

            st.session_state.favorite_queries = [
                q for q in st.session_state.favorite_queries if q["name"].lower() != favorite_name.lower()
            ]
            st.session_state.favorite_queries.insert(
                0,
                {
                    "name": favorite_name,
                    "sql": st.session_state.sql_text,
                    "preview": sql_preview(st.session_state.sql_text),
                    "saved_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
                },
            )
            st.session_state.favorite_queries = st.session_state.favorite_queries[:20]
            st.success(f"Consulta '{favorite_name}' salva nos favoritos.")

        if run_button:
            with st.spinner("Executando consulta na API..."):
                payload, raw_payload, err = call_sql_api(st.session_state.sql_text)
            st.session_state.last_raw_response = raw_payload
            st.session_state.last_error = err
            if err:
                st.session_state.last_result = None
                add_to_history(st.session_state.sql_text, success=False, result_df=None, error=err)
            else:
                st.session_state.last_result = normalize_to_dataframe(payload)
                add_to_history(
                    st.session_state.sql_text,
                    success=True,
                    result_df=st.session_state.last_result,
                    error=None,
                )


def render_assistant() -> None:
    with st.container(border=True):
        st.markdown('<div class="card-title">AI Assistant</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="card-caption">Descreva em linguagem natural e receba sugestão de SQL da sua API.</div>',
            unsafe_allow_html=True,
        )

        for msg in st.session_state.assistant_messages[-6:]:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
                if msg["role"] == "assistant" and msg.get("metadata_context"):
                    st.json(msg["metadata_context"])

        if st.session_state.assistant_pending_prompt:
            with st.chat_message("assistant"):
                st.markdown("_Processando resposta..._")
            with st.spinner("Consultando assistente..."):
                suggestion, metadata_context, err = call_assistant_api(
                    st.session_state.assistant_pending_prompt,
                    st.session_state.assistant_pending_sql or st.session_state.sql_text,
                )
            if err:
                st.session_state.assistant_messages.append({"role": "assistant", "content": err})
            else:
                if metadata_context:
                    st.session_state.assistant_messages.append(
                        {
                            "role": "assistant",
                            "content": "Retorno do MetadataRetrievalService:",
                            "metadata_context": metadata_context,
                            "message_type": "metadata",
                        }
                    )
                st.session_state.assistant_messages.append(
                    {
                        "role": "assistant",
                        "content": suggestion or "",
                        "message_type": "sql",
                    }
                )
            st.session_state.assistant_pending_prompt = None
            st.session_state.assistant_pending_sql = None
            st.rerun()

        prompt = st.chat_input("Ex.: trazer receita por mês dos últimos 12 meses")
        if prompt:
            st.session_state.assistant_messages.append({"role": "user", "content": prompt})
            st.session_state.assistant_pending_prompt = prompt
            st.session_state.assistant_pending_sql = st.session_state.sql_text
            st.rerun()

        if st.button("Usar última sugestão no editor", use_container_width=True):
            for msg in reversed(st.session_state.assistant_messages):
                if msg["role"] == "assistant" and msg.get("message_type") == "sql" and msg["content"].strip():
                    st.session_state.sql_text = msg["content"]
                    st.rerun()
                if (
                    msg["role"] == "assistant"
                    and msg.get("message_type") is None
                    and not msg.get("metadata_context")
                    and msg["content"].strip()
                ):
                    st.session_state.sql_text = msg["content"]
                    st.rerun()


def render_results() -> None:
    with st.container(border=True):
        st.markdown('<div class="card-title">Resultado</div>', unsafe_allow_html=True)
        st.markdown('<span class="chip">Formatação automática para tabela</span>', unsafe_allow_html=True)

        if st.session_state.last_error:
            st.error(st.session_state.last_error)
        elif st.session_state.last_result is None:
            st.info("Execute uma query para visualizar os resultados aqui.")
        else:
            result_df = st.session_state.last_result
            if result_df.empty:
                st.warning("A consulta executou, mas não retornou linhas.")
            else:
                st.dataframe(result_df, use_container_width=True, hide_index=True)

            with st.expander("Ver resposta bruta da API"):
                st.json(st.session_state.last_raw_response)


def render_history_and_favorites() -> None:
    left_col, right_col = st.columns(2, gap="medium")

    with left_col:
        with st.container(border=True):
            st.markdown('<div class="card-title">Histórico de Consultas</div>', unsafe_allow_html=True)

            if not st.session_state.query_history:
                st.info("Nenhuma execução ainda.")
            else:
                for idx, item in enumerate(st.session_state.query_history[:10]):
                    status_class = "history-ok" if item["success"] else "history-err"
                    row_text = f" | {item['rows']} linha(s)" if item["success"] else ""
                    st.markdown(
                        f'<div class="history-meta"><code>{item["timestamp"]}</code> | '
                        f'<span class="{status_class}">{"OK" if item["success"] else "ERRO"}</span>{row_text}</div>',
                        unsafe_allow_html=True,
                    )
                    st.code(item["preview"], language="sql")
                    if st.button("Recarregar no editor", key=f"hist_load_{idx}", use_container_width=True):
                        st.session_state.sql_text = item["sql"]
                        st.rerun()
                    if not item["success"] and item["error"]:
                        st.caption(item["error"])
                    st.divider()

    with right_col:
        with st.container(border=True):
            st.markdown('<div class="card-title">Consultas Favoritas</div>', unsafe_allow_html=True)

            if not st.session_state.favorite_queries:
                st.info("Nenhuma consulta salva ainda.")
            else:
                for idx, item in enumerate(st.session_state.favorite_queries):
                    st.markdown(f"**{item['name']}**")
                    st.caption(f"Salva em {item['saved_at']}")
                    st.code(item["preview"], language="sql")

                    fav_load_col, fav_remove_col = st.columns(2, gap="small")
                    with fav_load_col:
                        if st.button("Carregar", key=f"fav_load_{idx}", use_container_width=True):
                            st.session_state.sql_text = item["sql"]
                            st.rerun()
                    with fav_remove_col:
                        if st.button("Remover", key=f"fav_remove_{idx}", use_container_width=True):
                            st.session_state.favorite_queries = [
                                q for q in st.session_state.favorite_queries if q["name"] != item["name"]
                            ]
                            st.rerun()
                    st.divider()


def main() -> None:
    init_state()
    apply_styles()
    render_header()

    col_sql, col_ai = st.columns([2.05, 1.15], gap="medium")
    with col_sql:
        render_sql_editor()
    with col_ai:
        render_assistant()

    render_results()
    render_history_and_favorites()


if __name__ == "__main__":
    main()
