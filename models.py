# Importing requirements from config.py
from config import List, BaseModel, Field

# Creating Pydantic models for output.

# For wrapping each sub-question given by the decomposer.
class SubQuestions(BaseModel):
    question: str = Field(default="", description="Specific, answerable sub-question grounded in the schema.")
    chart_type: str = Field(default="", description="The chart type of the sub-question grounded in the schema.")
    reason: str = Field(default="", description="Reason why the chart type fits this question.")
    route: str = Field(default="SQL", description="SQL for structured data queries, SEMANTIC for qualitative questions.")



# For Decomposed Questions, to capture the full json response from the LangChain.
class DecomposedQuestions(BaseModel):
    questions: List[SubQuestions] = Field(default_factory=list, description="List of 1-4 non-overlapping questions from the schema.")



# For generating charts
class GenerationOutput(BaseModel):
    sql_query: str = Field(default="", description="SQL query for generation output. Only SELECT queries are valid.")
    chart_code: str = Field(
        default="",
        description="Plotly python code operating on the input dataframes, assigning the result to 'fig', Use 'fig == None' if not graphable."
    )
    insight: str = Field(
        default="",
        description="2-3 analytical bullet points (starting with •) based on what the SQL query will likely return."
    )



# For checking the sufficiency of the answers
class SufficiencyCheck(BaseModel):
    sufficient: bool = Field(default=True, description="True if the results are enough to answer the original query.")
    missing: str = Field(default="", description="What is still needed to answer the original query.")



print("[MODELS] Pydantic Models Defined.")