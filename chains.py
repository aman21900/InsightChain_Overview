# Importing requirements from config.py & models.py
from config import STRUCTURED_MODEL, GENERATION_MODEL, MAX_OUTPUT_TOKENS
from config import ChatPromptTemplate
from config import ChatGroq
from config import JsonOutputParser, StrOutputParser
from config import os
from models import DecomposedQuestions, GenerationOutput, SufficiencyCheck



def build_decomposer_chain():
    """
    Splits user query into sub-questions, each with chart_type and route.
    """
    system_prompt = """\
You are a business intelligence query planner and dashboard designer.
Your job is to decompose a user's high-level question into specific, answerable sub-questions,
each designed to produce a meaningful dashboard panel.

RELEVANT SCHEMA CONTEXT (tables and columns available in the database):
{schema_context}

CHART TYPE RULES — pick the most appropriate type for each sub-question:
- bar        - comparing a metric across categories (eg: suppliers, products, regions)
- line       - a metric changing over time (eg: monthly, weekly, daily trends)
- pie        - proportions or shares that add up to a whole
- scatter    - relationship or correlation between two numeric columns
- histogram  - distribution of a single numeric column (e.g. order values, lead times)
- box        - spread and outliers of a metric across categories
- heatmap    - intensity of a metric across two categorical dimensions
- funnel     - sequential stages where volume drops at each step
- treemap    - hierarchical part-to-whole breakdown
- waterfall  - cumulative effect of sequential positive/negative values
- table_only - the answer is best shown as a table, no chart needed

ROUTE RULES — set route for each sub-question:
- SQL      - numbers, counts, totals, averages, rankings, filters, comparisons, date ranges
- SEMANTIC - summaries, advice, explanations, qualitative descriptions, open-ended analysis
- When uncertain, choose SQL.

RULES:
- Generate between 1 and {max_questions} sub-questions.
- Each sub-question must be answerable using the tables and columns listed above.
- Sub-questions must NOT overlap — each should cover a distinct aspect.
- Do NOT invent tables or columns that are not listed above.

Respond ONLY with valid JSON. No preamble, no explanation outside the JSON:
{{"questions": [
  {{"question": "...", "chart_type": "bar", "reason": "...", "route": "SQL"}},
  {{"question": "...", "chart_type": "line", "reason": "...", "route": "SQL"}}
]}}
"""
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "User question: {user_query}")
    ])
    llm = ChatGroq(
        model=STRUCTURED_MODEL,
        temperature=0.01,
        api_key=os.getenv("GROQ_API_KEY")
    )
    return prompt | llm | JsonOutputParser(pydantic_object=DecomposedQuestions)



def build_sql_chain():
    """Generates SQL + chart code + insight in a single LLM call."""
    system_prompt = """\
    You are an expert SQLite analyst and Python visualisation engineer.

    DATABASE SCHEMA (authoritative — every table and every column that exists):
    {schema_context}

    The schema format is: Table 'table_name': [col1 (TYPE), col2 (TYPE), ...]
    A column ONLY exists if it is listed under that specific table.
    If a column is not listed under a table, it does NOT exist — never use it there.

    SEMANTICALLY CLOSEST COLUMNS TO THIS QUERY (hints only — verify against schema above):
    {column_hints}

    INTERNAL VERIFICATION — complete these steps mentally before writing any SQL. Do NOT include them in your output:
      Step 1 — List every table you plan to use.
      Step 2 — For each table, copy its exact column list from the schema.
      Step 3 — For each column you SELECT, filter, or JOIN on, confirm it appears in THAT table's list.
                If it does not, find the correct table and JOIN there.
      Step 4 — If the question cannot be answered because a required column or time dimension
                does not exist in any table, set sql_query to empty string "".
      Step 5 — Write the final query plan with table aliases.

    Your job is to produce a SINGLE JSON object with ONLY TWO fields:
    - "sql_query": a valid SQLite SELECT query, or empty string "" if unanswerable with the schema
    - "chart_code": Plotly Python code using chart type '{chart_type}', operating on a DataFrame
      named 'df', assigning the result to 'fig'. Write exactly: fig = None if sql_query is empty
      or the result is not graphable.

    SQL RULES:
    - Use ONLY native SQLite syntax
    - ONLY SELECT statements. Never DROP, DELETE, INSERT, UPDATE, ALTER, TRUNCATE
    - NEVER use a column in a table unless it appears in that table's column list in the schema
    - ALWAYS alias aggregated/computed columns with clean snake_case names e.g. SUM(x) AS total_x
    - When joining, qualify every column with its table alias e.g. s.supplier_id not just supplier_id
    - UNION ALL rule: never put ORDER BY inside individual branches — wrap the UNION in a subquery:
      SELECT * FROM (...UNION ALL...) ORDER BY ...

    CHART RULES:
    - Use px.{chart_type}() as your primary chart function
    - DataFrame variable is named exactly 'df'
    - Figure variable must be named exactly 'fig'
    - Add a clean title and axis labels
    - No import statements — pandas, plotly.express as px, and plotly.graph_objects as go are available
    - Every column name in chart_code must exactly match an alias or column from your SELECT clause

    CRITICAL OUTPUT RULES:
    - Output ONLY one single JSON object — no markdown, no preamble, no explanation outside the JSON
    - Escape internal double quotes with \\"
    - Use \\n for newlines inside string values
    - DO NOT split a single string value into multiple quoted segments across lines. Keep the value as a single enclosed string.  
    - The entire response must be parseable by json.loads()

    {{"sql_query": "SELECT ...", "chart_code": "fig = px.{chart_type}(df, ...)"}}
    """

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "Question: {sub_question}")
    ])
    llm = ChatGroq(
        model=GENERATION_MODEL,
        temperature=0.01,
        api_key=os.getenv("GROQ_API_KEY"),
        max_tokens=MAX_OUTPUT_TOKENS
    )
    return prompt | llm | JsonOutputParser(pydantic_object=GenerationOutput)



def build_sql_repair_chain():
    """
    Repairs a previously failed SQL query.
    Receives the original question, the failed query, and the exact error message,
    and produces a corrected sql_query + chart_code + insight in one call.
    Reuses GenerationOutput — same four-field shape as build_sql_chain.

    CONVERGENCE: this chain is prone to rumination — proposing a corrected query,
    then second-guessing it, looping until the token budget is exhausted before
    ever writing to sql_query. The prompt forbids this explicitly and max_tokens
    caps output as a hard guardrail.
    """
    system_prompt = """\
You are an expert SQLite analyst and Python visualisation engineer.
A SQL query you wrote FAILED. Diagnose the cause from the error below and produce ONE
corrected query — no second-guessing.
 
DATABASE SCHEMA (authoritative):
{schema_context}
 
Format: Table 'name': [col (TYPE), ...]. A column exists ONLY in tables where it's listed.
 
CLOSEST COLUMN HINTS (verify against schema above):
{column_hints}
 
CHART TYPE: '{chart_type}'
 
FAILED QUERY:
{previous_sql}
 
ERROR:
{error_message}
 
INTERNAL DIAGNOSIS — complete these steps mentally. Do NOT include them in your output:
  Step 1 — Read the error message and identify the exact cause.
  Step 2 — List every table you plan to use in the corrected query.
  Step 3 — For each table, copy its exact column list from the schema.
  Step 4 — Confirm every column in your corrected query appears in the right table's list.
  Step 5 — If the error reveals the question is fundamentally unanswerable, set sql_query to "".
  Step 6 — Write the corrected query plan with table aliases.
 
CONVERGENCE — read carefully: propose exactly ONE corrected query in step 3. No "however",
"but", "wait", or alternative attempts — whatever you write is final, commit to it. Keep
reasoning brief; do not restate the full schema.

Produce a SINGLE JSON object with two fields:

"sql_query" — corrected valid SQLite SELECT, or "" if truly unanswerable.
 
"chart_code" — Plotly code, chart type '{chart_type}', df='df', result='fig'. Column names
  MUST match the corrected query's SELECT aliases (they may differ from the failed query).
  fig = None if sql_query is empty or ungraphable.
 
SQL RULES:
- SQLite syntax, SELECT only — never DROP/DELETE/INSERT/UPDATE/ALTER/TRUNCATE
- Only use a column in a table if it's listed under THAT table in the schema
- Alias aggregates with snake_case: SUM(x) AS total_x
- Qualify columns with table aliases when joining: s.supplier_id, not supplier_id
- MAX+MIN PATTERN — to get the single highest-value row AND the single lowest-value row of a
  metric in one result (e.g. "best and worst supplier"):
    SELECT * FROM (SELECT ... FROM table ORDER BY metric DESC LIMIT 1)
    UNION ALL
    SELECT * FROM (SELECT ... FROM table ORDER BY metric ASC LIMIT 1)
  No outer ORDER BY/LIMIT after the UNION ALL — that discards one of the rows.
 
CRITICAL OUTPUT RULES:
- ONE JSON object only, no markdown or extra text.
- DO NOT split a single string value into multiple quoted segments across lines. Keep the value as a single enclosed string.
- Escape internal quotes with \\", use \\n for newlines. Must be valid for json.loads().
 
{{"sql_query": "SELECT ...", "chart_code": "fig = px.{chart_type}(df, ...)"}}
"""
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "Original question: {sub_question}")
    ])
    llm = ChatGroq(
        model=GENERATION_MODEL,
        temperature=0.01,
        api_key=os.getenv("GROQ_API_KEY"),
        max_tokens=MAX_OUTPUT_TOKENS
    )
    return prompt | llm | JsonOutputParser(pydantic_object=GenerationOutput)


def build_semantic_chain():
    """Answers qualitative questions using retrieved context."""
    system_prompt = """\
    You are an Operations Analytics Advisor with access to real business data.

    RETRIEVED DATA CONTEXT:
    {retrieved_context}

    Instructions:
    - Use ONLY the retrieved data above as your source of truth.
    - Reference specific values and patterns visible in the data.
    - Be analytical, concise, and actionable.
    - If the data is insufficient, say so explicitly. Do NOT fabricate numbers.
    - Do not show thinking process.
    - Do not write any preamble. No placeholders.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "Question: {sub_question}")
    ])
    llm = ChatGroq(model=GENERATION_MODEL, temperature=0.01, api_key=os.getenv("GROQ_API_KEY"))
    return prompt | llm | StrOutputParser()



def build_mini_insight_chain():
    """To write insights about the tables created."""
    system_prompt = """\
    You are a senior business intelligence analyst.

    RETRIEVED TABLE DATA:
    {retrieved_table_data}

    You have been given the data table in order to answer a user's question.
    Write 2-3 analytical bullet points (each starting with •) explaining what can be inferred from the data.
    If the table is empty, explain what data is missing.

    RULES:
    - Reference specific numbers from the table.
    - Do NOT repeat the same insight across different bullets.
    - Do NOT fabricate numbers not present in the data.
    - Be analytical and actionable.
    - Do not start with an introduction/preamble or any placeholders.
    """
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "Question : {sub_question}")
    ])
    # llm = ChatHuggingFace(llm=HuggingFaceEndpoint(
    #     repo_id=GENERATION_MODEL, temperature=0.3,
    #     max_new_tokens=768, huggingfacehub_api_token=HF_TOKEN
    # ))
    llm = ChatGroq(
        model=GENERATION_MODEL,
        temperature=0.01,
        api_key=os.getenv("GROQ_API_KEY")
    )
    return prompt | llm | StrOutputParser()



def build_sufficiency_chain():
    """Qwen2.5 — checks if collected results sufficiently answer the original query."""
    system_prompt = """\
You are a quality reviewer for business intelligence reports.
Given the original user question and a summary of data collected so far,
decide if the data is sufficient to produce a complete, useful dashboard.
 
RESULTS COLLECTED SO FAR:
{results_summary}
 
Respond ONLY with this exact JSON structure. No preamble, no explanation:
{{"sufficient": true, "missing": ""}}
or
{{"sufficient": false, "missing": "description of what is still needed"}}
 
Rules:
- "sufficient" must be a boolean: true or false
- "missing" must always be a string key; empty string "" when sufficient is true
- Be STRICT: only return false if a core aspect of the original question is completely
  unaddressed. Do NOT request broader coverage or extra metrics not explicitly asked for.
- If every distinct aspect of the question has at least one result with data, return true.
- A single failed sub-question is NOT grounds for false if the topic is otherwise covered.
"""
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "Original question: {user_query}")
    ])
    # llm = ChatHuggingFace(llm=HuggingFaceEndpoint(
    #     repo_id=STRUCTURED_MODEL, temperature=0.01,
    #     max_new_tokens=128, huggingfacehub_api_token=HF_TOKEN
    # ))
    llm = ChatGroq(
        model=STRUCTURED_MODEL,
        temperature=0.01,
        api_key=os.getenv("GROQ_API_KEY")
    )
    return prompt | llm | JsonOutputParser(pydantic_object=SufficiencyCheck)



def build_reducer_chain():
    """Llama-3 — synthesises all sub-results into a coherent narrative."""
    system_prompt = """\
You are a senior business intelligence analyst writing an executive summary.

You have been given the results of multiple data queries run to answer a user's question.
Write a coherent 3-5 paragraph narrative that synthesises all findings.

RULES:
- Reference specific numbers from the results below.
- Do NOT repeat the same insight across paragraphs.
- Do NOT fabricate numbers not present in the data.
- Be analytical and actionable.

ALL QUERY RESULTS AND INSIGHTS:
{all_results}
"""
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "Original user question: {user_query}")
    ])
    # llm = ChatHuggingFace(llm=HuggingFaceEndpoint(
    #     repo_id=GENERATION_MODEL, temperature=0.3,
    #     max_new_tokens=768, huggingfacehub_api_token=HF_TOKEN
    # ))
    llm = ChatGroq(
        model=GENERATION_MODEL,
        temperature=0.01,
        api_key=os.getenv("GROQ_API_KEY")
    )
    return prompt | llm | StrOutputParser()

print("[CHAINS] All chain builders defined.")