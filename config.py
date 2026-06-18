# Importing required libraries

import os
import re
import csv
import time
import sqlite3
import builtins
import json
from pathlib import Path
from typing import Tuple, Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import sqlparse
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio
import gradio as gr
from dotenv import load_dotenv
from pydantic import BaseModel, Field
import docx
from docx import Document as DocxDocument
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.documents import Document
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_chroma import Chroma

from langchain_groq import ChatGroq # for using Groq
from langchain_huggingface import HuggingFaceEmbeddings
# from langchain_huggingface import HuggingFaceEndpoint, HuggingFaceEmbeddings, ChatHuggingFace # for using HuggingFaceHub



# Loading the environment variables
load_dotenv()
HF_TOKEN = os.getenv("HF_TOKEN")
print("[ENVIRONMENT] Environment Variables Imported.")



# Setting the path constants
base_dir = Path(__file__)

DB_PATH          = base_dir.parent / "db/operations_analytics.db"
DB_DIR           = base_dir.parent / "db"
CHROMA_PATH      = base_dir.parent / "chroma_index/vectorstore"
SPREADSHEETS_DIR = base_dir.parent / "data"
DOCUMENTS_DIR    = base_dir.parent / "documents"



# Setting threshold constants
SCHEMA_CACHE_TTL = 300      # Timer to control how long a cached value is considered to be fresh. Here it is 5 mins.
                            # Everytime the schema context is buil, the result is stored in the memory along with the timestamp. So, instead of hitting the database on every LLM call (which can quickly escalate), the schema context is refreshed every SCHEMA_CACHE_TTL seconds.
MAX_SUBQUESTIONS = 3        # Maximum sub-questions which the LLM can make on original user query.
                            # Part of Iterative Chain-of-Thought (ICoT) process.
CONCURRENCY_CAP = 2         # How many concurrent threads will run at one time.

MAX_FOLLOW_UP_QUESTIONS = 2 # Maximum number fo follow up questions the agent will ask.



# Setting model roles
# STRUCTURED_MODEL    = "Qwen/Qwen2.5-7B-Instruct"            # strict JSON tasks
# GENERATION_MODEL    = "meta-llama/Meta-Llama-3-8B-Instruct" # long generation task
STRUCTURED_MODEL = "llama-3.3-70b-versatile"
GENERATION_MODEL = 'llama-3.1-8b-instant'



# Creating the required directories
Path(DB_DIR).mkdir(parents=True, exist_ok=True)
Path(CHROMA_PATH).mkdir(parents=True, exist_ok=True)



print("[ENVIRONMENT] Paths to directories and models set.")
