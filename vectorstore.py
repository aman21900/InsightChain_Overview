# Building the unified vectorstore
# Indexes:
# - Schema descriptions — LLM-generated table summaries + column metadata (`source_type=structured, retrieval_hint=schema`)
# - Data rows — sampled rows as natural language sentences (`source_type=structured, retrieval_hint=data`)
# - Document chunks — DOCX files chunked into ~500 word segments (`source_type=document, retrieval_hint=chunk`)

# Importing requirements from config.py & database.py
from config import DOCUMENTS_DIR, CHROMA_PATH
from config import HuggingFaceEmbeddings
from config import Chroma
from config import Optional, Any, Dict, List
from config import STRUCTURED_MODEL
from config import ChatGroq
from config import Document
from config import os, re, json, pd, Path
from config import DocxDocument, CT_P, CT_Tbl, docx
from database import DatabaseManager



class UnifiedVectorStore:
    """
    Single ChromaDB collection for both structured (CSV/DB) and document (DOCX) data.
    Tagged with source_type and retrieval_hint metadata for filtered retrieval.
    """
    COLLECTION_NAME = "unified_index"
    MAX_ROWS_PER_TABLE = 3
    CHUNK_SIZE = 500          # words per document chunk
    CHUNK_OVERLAP = 50        # words of overlap between chunks



    def __init__(self):
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        self.vector_store: Optional[Chroma] = None
        self._schema_desc_llm = None   # lazy init for, the description of the tables, written by the LLM.



    def _get_schema_desc_llm(self):
        """Lazy-init a small LLM for generating table purpose descriptions."""
        if self._schema_desc_llm is None:
            # self._schema_desc_llm = ChatHuggingFace(llm=HuggingFaceEndpoint(
            #     repo_id=STRUCTURED_MODEL,
            #     temperature=0.1,
            #     max_new_tokens=1024,
            #     huggingfacehub_api_token=HF_TOKEN
            # ))
            self._schema_desc_llm = ChatGroq(
                model = STRUCTURED_MODEL,
                temperature=0.1,
                api_key=os.getenv("GROQ_API_KEY"),
            )
        return self._schema_desc_llm



    def _generate_schema_description(self, table_name: str, columns: List[Dict]) -> str:
        """
        Ask the LLM to write a one-sentence description of the table's purpose.
        Falls back to a template string if LLM call fails.
        """
        # Extracting column names, to help LLM to write schema description.
        col_names = ", ".join(c["name"] for c in columns)

        # Extracting sample data from the table to help LLM to write schema description.
        sample_data = DatabaseManager.sample_table(table_name, self.MAX_ROWS_PER_TABLE)

        try:
            llm = self._get_schema_desc_llm()
            prompt = (
                f"In one sentence, describe the business purpose of a database table named '{table_name}' "
                f"that has these columns: {col_names}. "
                f"This is the sample data from the table '{table_name}': \n {sample_data} "
                f"Be specific and concise. Do not mention SQL or technical details."
                f"Strictly do not mention any numerical value/data from the given sample. The table data is strictly confidential."
            )
            response = llm.invoke(prompt)

            # Extract text content from response
            if hasattr(response, 'content'):
                return response.content.strip()
            return str(response).strip()
        except Exception as e:
            print(f"[VS] Schema description LLM failed for '{table_name}': {e}")
            return f"Table '{table_name}' contains data with columns: {col_names}."



    def _generate_column_description(self, table_name: str, columns: List[Dict]) -> str:
        """Ask the LLM to write a one-sentence description for each column."""

        batch_size = 8
        all_descs = {}

        for i in range(0, len(columns), batch_size):
            batch = columns[i: i+batch_size]

            # Extracting the column names and data types, to help LLM to write description based on the data.
            col_data = ", ".join(f"Column: {c['name']} ({c['type']}) form the Table {table_name}" for c in batch)

            # Sample the table, to help the LLM to write column descriptions based on the data.
            sample_df = DatabaseManager.sample_table(table_name, self.MAX_ROWS_PER_TABLE)

            try:
                llm = self._get_schema_desc_llm()
                prompt = (
                    f"In one sentence, describe the business purpose of each column of the list: {col_data}. "
                    f"Each column is present in the table {table_name}."
                    f"This is the sample data for the table {table_name}: \n{sample_df} "
                    f"Be specific and concise. Do not mention SQL or technical details."
                    f"Strictly do not mention any numerical value/data from the given sample. The table data is strictly confidential."
                    f"Strictly output ONLY a valid JSON dictionary. "
                    f"No preamble, no explanation, no markdown fences. "
                    f"The first character of your response must be {{ and the last must be }}"
                )
                response = llm.invoke(prompt)

                # Extract text from the response
                if hasattr(response, 'content'):
                    raw = response.content.strip()
                else:
                    raw = str(response).strip()

                raw = re.sub(r"```(?:json)?", "", raw).strip()
                start = raw.find("{")
                end   = raw.rfind("}") + 1
                if start != -1 and end > 0:
                    batch_descs = json.loads(raw[start:end])
                    all_descs.update(batch_descs)
                else:
                    raise ValueError("No JSON object found in response")

            except Exception as e:
                print(f"[VS] Column description LLM failed for batch {i} of '{table_name}': {e}")
                for c in batch:
                    all_descs[c['name']] = f"Column '{c['name']}' in table '{table_name}'."
        return json.dumps(all_descs, indent=4)



    @staticmethod
    def _chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
        """Split text into overlapping word-based chunks, to be passed on to create word embeddings."""
        words = text.split()
        chunks = []
        start = 0
        while start < len(words):
            end = min(start + chunk_size, len(words))
            chunks.append(" ".join(words[start:end]))
            if end == len(words):
                break
            start += chunk_size - overlap
        return chunks



    @staticmethod
    def _extract_docx_text(path: Path) -> str:
        """Extract all text (paragraphs and tables) from a DOCX file."""
        doc_data = ""
        try:
            doc = DocxDocument(str(path))
            # Check if the text portion is paragraph or table
            for element in doc.element.body:
                if isinstance(element, CT_P):
                    p = docx.text.paragraph.Paragraph(element, doc)
                    if p.text.strip():
                        doc_data = doc_data + "\n" + p.text.strip()
                if isinstance(element, CT_Tbl):
                    table_data = ""
                    p = docx.table.Table(element, doc)
                    table_data = table_data + "Table Start - \n"
                    for row in p.rows:
                        table_data = table_data + "\n" + "|".join([cell.text.strip() for cell in row.cells])
                    table_data = table_data + "\nTable End - \n"
                    doc_data = doc_data + "\n" + table_data

            return doc_data
        except Exception as e:
            print(f"[VS] Could not read DOCX '{path.name}': {e}")
            return ""



    def build_index(self) -> None:
        """
        Full index build:
          1. Descriptions (LLM-generated) for each table
          2. Column-level metadata for semantic entity resolution
          3. DOCX document chunks
        """
        documents = []

        # -- STRUCTURED DATA ---------------------------------------------------
        tables = DatabaseManager.get_all_tables()
        for table_name in tables:
            columns = DatabaseManager.get_table_columns(table_name)

            # 1. LLM-generated schema description
            print(f"[VS] Generating description for table '{table_name}'...")
            desc = self._generate_schema_description(table_name, columns)
            print(desc)
            documents.append(Document(
                page_content=f"Table '{table_name}': {desc}",
                metadata={"source_type": "structured", "retrieval_hint": "schema",
                           "table": table_name, "doc_type": "schema_description"}
            ))

            # 2. Column-level metadata entries
            print(f"[VS] Generating description for the columns for the table '{table_name}'...")
            col_descs = self._generate_column_description(table_name, columns)
            print(col_descs)
            col_descs = json.loads(col_descs) # Converting the string of column and their descriptions into dictionary.

            for col in columns:
                if col['name'] in col_descs.keys():
                    documents.append(Document(
                        page_content=f"Column '{col['name']}' ({col['type']}) in table '{table_name}'."
                                     f"Column Description: {col_descs[col['name']]}",
                        metadata={"source_type": "structured", "retrieval_hint": "schema",
                                   "table": table_name, "column": col["name"], "doc_type": "column_entry"}
                    ))


        # -- DOCUMENTS ---------------------------------------------------------
        docx_files = list(Path(DOCUMENTS_DIR).glob("*.docx"))
        for docx_path in docx_files:
            text = self._extract_docx_text(docx_path)
            if not text.strip():
                continue
            chunks = self._chunk_text(text, self.CHUNK_SIZE, self.CHUNK_OVERLAP)
            for i, chunk in enumerate(chunks):
                documents.append(Document(
                    page_content=chunk,
                    metadata={"source_type": "document", "retrieval_hint": "chunk",
                               "filename": docx_path.name, "chunk_index": i, "doc_type": "docx_chunk"}
                ))
            print(f"[VS] '{docx_path.name}' — {len(chunks)} chunks indexed")


        # -- BUILD CHROMA VECTORSTORE ------------------------------------------
        print(f"[VS] Embedding {len(documents)} total documents into ChromaDB...")
        self.vector_store = Chroma.from_documents(
            documents=documents,
            embedding=self.embeddings,
            persist_directory=CHROMA_PATH,
            collection_name=self.COLLECTION_NAME
        )
        print(f"[VS] Index built — {len(documents)} documents stored.")



    def load_existing(self) -> bool:
        """Load a previously built index from disk. Returns True if successful."""
        try:
            self.vector_store = Chroma(
                persist_directory=CHROMA_PATH,
                embedding_function=self.embeddings,
                collection_name=self.COLLECTION_NAME
            )
            count = self.vector_store._collection.count()
            if count == 0:
                return False
            print(f"[VS] Loaded existing index — {count} documents.")
            return True
        except Exception:
            return False



    def retrieve_schema_context(self, query: str, top_k: int = 5) -> str:
        """Retrieve top-k schema descriptions for the decomposer. SQL track only."""

        results = self.vector_store.similarity_search(
            query,
            k=top_k,
            filter={
                "$and": [
                    {"source_type": {"$eq": "structured"}},
                    {"retrieval_hint": {"$eq": "schema"}},
                    {"doc_type": {"$eq": "schema_description"}}
                ]
            }
        )
        return "\n".join(doc.page_content for doc in results)



    def retrieve_column_hints(self, query: str, top_k: int = 4) -> str:
        """Retrieve the closest column names for SQL entity resolution."""

        results = self.vector_store.similarity_search(
            query, k=top_k,
            filter={
                "$and": [
                    {"source_type": {"$eq": "structured"}},
                    {"retrieval_hint": {"$eq": "schema"}},
                    {"doc_type": {"$eq": "column_entry"}}
                ]
            }
        )
        lines = [
            f"  - {d.page_content}"
            for d in results
        ]
        return "Semantically closest columns:\n" + "\n".join(lines) if lines else ""



    def retrieve_semantic_context(self, query: str, top_k: int = 15) -> str:
        """Retrieve top-k relevant rows/chunks from both structured and document sources.
        Column and schema descriptions serve as structured context for qualitative questions.
        """

        chroma_filter: Any = {
            "$or": [
                {"doc_type": {"$eq":"column_entry"}},
                {"doc_type": {"$eq":"docx_chunk"}},
                {"doc_type": {"$eq":"schema_description"}}
            ]
        }
        results = self.vector_store.similarity_search(
            query,
            k=top_k,
            filter=chroma_filter
        )
        return "\n".join(doc.page_content for doc in results)



print("[VS] UnifiedVectorStore defined.")