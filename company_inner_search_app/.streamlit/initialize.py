"""
このファイルは、最初の画面読み込み時にのみ実行される初期化処理が記述されたファイルです。
"""

############################################################
# ライブラリの読み込み
############################################################
import os
import sys
import logging
from logging.handlers import TimedRotatingFileHandler
from uuid import uuid4
import unicodedata
from pathlib import Path

from dotenv import load_dotenv
import streamlit as st

from langchain_community.document_loaders import (
    WebBaseLoader, PyPDFLoader, Docx2txtLoader, CSVLoader, TextLoader
)
from langchain_text_splitters import RecursiveCharacterTextSplitter

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=ct.CHUNK_SIZE,
    chunk_overlap=ct.CHUNK_OVERLAP
)

from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import Chroma

# 任意課題（社員名簿の統合用）
import pandas as pd
from langchain.schema import Document

import constants as ct


############################################################
# 設定関連
############################################################
# 「.env」ファイルで定義した環境変数の読み込み
load_dotenv()


############################################################
# 関数定義
############################################################

def initialize():
    """
    画面読み込み時に実行する初期化処理
    """
    initialize_session_state()  # 初期化データ
    initialize_session_id()     # セッションID
    initialize_logger()         # ログ設定
    initialize_retriever()      # RAG Retriever


def initialize_logger():
    """
    ログ出力の設定
    """
    os.makedirs(ct.LOG_DIR_PATH, exist_ok=True)
    logger = logging.getLogger(ct.LOGGER_NAME)

    # 二重登録防止
    if logger.hasHandlers():
        return

    log_handler = TimedRotatingFileHandler(
        os.path.join(ct.LOG_DIR_PATH, ct.LOG_FILE),
        when="D",
        encoding="utf8"
    )
    formatter = logging.Formatter(
        f"[%(levelname)s] %(asctime)s line %(lineno)s, in %(funcName)s, session_id={st.session_state.session_id}: %(message)s"
    )
    log_handler.setFormatter(formatter)
    logger.setLevel(logging.INFO)
    logger.addHandler(log_handler)


def initialize_session_id():
    """
    セッションIDの作成
    """
    if "session_id" not in st.session_state:
        st.session_state.session_id = uuid4().hex


def initialize_session_state():
    """
    初期化データの用意
    """
    if "messages" not in st.session_state:
        st.session_state.messages = []      # 画面表示用
        st.session_state.chat_history = []  # LLM用


def initialize_retriever():
    """
    画面読み込み時にRAGのRetriever（ベクターストアから検索するオブジェクト）を作成
    """
    logging.getLogger(ct.LOGGER_NAME)  # ロガー登録

    if "retriever" in st.session_state:
        return

    # 1) データ読み込み（ローカル + Web）
    docs_all = load_data_sources()

    # 2) Windows向け文字列調整
    for doc in docs_all:
        doc.page_content = adjust_string(doc.page_content)
        for key in list(doc.metadata.keys()):
            doc.metadata[key] = adjust_string(doc.metadata[key])

    # 3) 埋め込みモデル
    embeddings = OpenAIEmbeddings()

    # 4) チャンク分割（課題2：定数化）
    text_splitter = CharacterTextSplitter(
        chunk_size=ct.CHUNK_SIZE,
        chunk_overlap=ct.CHUNK_OVERLAP,
        separator="\n"
    )
    splitted_docs = text_splitter.split_documents(docs_all)

    # 5) ベクターストア
    db = Chroma.from_documents(splitted_docs, embedding=embeddings)

    # 6) Retriever（課題1：TOP_K=5）
    st.session_state.retriever = db.as_retriever(search_kwargs={"k": ct.TOP_K})


def load_data_sources():
    """
    RAGの参照先となるデータソースの読み込み
    Returns:
        読み込んだデータソース（list[Document]）
    """
    docs_all = []

    # ローカル（再帰で走査）
    recursive_file_check(ct.RAG_TOP_FOLDER_PATH, docs_all)

    # Web
    web_docs_all = []
    for web_url in ct.WEB_URL_LOAD_TARGETS:
        loader = WebBaseLoader(web_url)
        web_docs = loader.load()
        web_docs_all.extend(web_docs)
    docs_all.extend(web_docs_all)

    return docs_all


def recursive_file_check(path, docs_all):
    """
    フォルダ/ファイルを再帰的に読み込み
    """
    if os.path.isdir(path):
        for name in os.listdir(path):
            full = os.path.join(path, name)
            recursive_file_check(full, docs_all)
    else:
        file_load(path, docs_all)


def _load_and_merge_staff_csv(csv_path: str):
    """
    任意課題：社員名簿.csv を1ドキュメントに統合して精度UP
    """
    df = pd.read_csv(csv_path)
    lines = []
    for _, r in df.iterrows():
        lines.append(
            f"部署:{r.get('部署','')} 氏名:{r.get('氏名','')} 役職:{r.get('役職','')} メール:{r.get('メール','')}"
        )
    big_text = "\n".join(lines)
    return [Document(page_content=big_text, metadata={"source": csv_path, "kind": "merged_csv"})]


def file_load(path, docs_all):
    """
    単一ファイルの読み込み
    """
    ext = os.path.splitext(path)[1].lower()
    fname = os.path.basename(path)

    if ext == ".pdf":
        docs_all.extend(PyPDFLoader(path).load())
    elif ext == ".docx":
        docs_all.extend(Docx2txtLoader(path).load())
    elif ext == ".csv":
        # 任意課題：社員名簿だけは統合読み
        if fname == "社員名簿.csv":
            docs_all.extend(_load_and_merge_staff_csv(path))
        else:
            docs_all.extend(CSVLoader(path).load())
    elif ext == ".txt":
        # 課題5：txt も取り込む（UTF-8想定）
        docs_all.extend(TextLoader(path, encoding="utf-8").load())
    else:
        # 想定外の拡張子はスキップ
        pass


def adjust_string(s):
    """
    Windows環境でRAGが正常動作するよう調整
    """
    if not isinstance(s, str):
        return s
    if sys.platform.startswith("win"):
        s = unicodedata.normalize('NFC', s)
        s = s.encode("cp932", "ignore").decode("cp932")
        return s
    return s
