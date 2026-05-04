# SQL Editor Frontend

Interface em Streamlit para simular uma IDE de banco com:

- editor SQL
- assistente de IA para montar query
- área de resultados formatados
- histórico de consultas executadas
- consultas favoritas salvas em sessão
- integração pronta para API backend

## Como rodar

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Endpoints esperados (backend)

Base da API lida do Streamlit secrets:

```toml
[api]
base_url = "http://localhost:8080"
```

O frontend está preparado para chamar:

- `POST /sql/run` com payload:
  ```json
  { "sql": "SELECT * FROM tabela" }
  ```
- `POST /assistant/text-to-sql-query` com payload:
  ```json
  {
    "prompt": "quero top 10 clientes",
    "currentSql": "SELECT ..."
  }
  ```

## Contrato de resposta esperado

O frontend está alinhado ao padrão:

```json
{
  "success": true,
  "data": {},
  "error": null,
  "meta": {
    "timestamp": "2026-04-17T18:00:00Z",
    "traceId": "uuid"
  }
}
```

Também há fallback para formato legado de payload direto.
