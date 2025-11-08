"""
このファイルは、画面表示以外の様々な関数定義のファイルです。
"""

############################################################
# ライブラリの読み込み
############################################################
from dotenv import load_dotenv
import streamlit as st

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage

from langchain_openai import ChatOpenAI
from langchain.chains.history_aware_retriever import create_history_aware_retriever
from langchain.chains.retrieval import create_retrieval_chain
from langchain.chains.combine_documents import create_stuff_documents_chain

import constants as ct


############################################################
# 設定関連
############################################################
load_dotenv()


############################################################
# 関数定義
############################################################

def get_source_icon(source: str):
    """
    メッセージと一緒に表示するアイコンの種類を取得
    """
    if str(source).startswith("http"):
        return ct.LINK_SOURCE_ICON
    return ct.DOC_SOURCE_ICON


def build_error_message(message):
    """
    エラーメッセージと管理者問い合わせテンプレートの連結
    """
    return "\n".join([message, ct.COMMON_ERROR_MESSAGE])


def get_llm_response(chat_message):
    """
    LLMからの回答取得
    """
    llm = ChatOpenAI(model_name=ct.MODEL, temperature=ct.TEMPERATURE)

    # 履歴を踏まえて「独立した質問」に整形
    question_generator_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", ct.SYSTEM_PROMPT_CREATE_INDEPENDENT_TEXT),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}")
        ]
    )

    # モードによって回答用プロンプトを切替
    qa_system_prompt = (
        ct.SYSTEM_PROMPT_DOC_SEARCH
        if st.session_state.mode == ct.ANSWER_MODE_1
        else ct.SYSTEM_PROMPT_INQUIRY
    )
    question_answer_prompt = ChatPromptTemplate.from_messages(
        [
            ("system", qa_system_prompt),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}")
        ]
    )

    # Retriever（履歴考慮）
    history_aware_retriever = create_history_aware_retriever(
        llm, st.session_state.retriever, question_generator_prompt
    )

    # 回答Chain
    question_answer_chain = create_stuff_documents_chain(llm, question_answer_prompt)

    # 「RAG × 会話履歴」
    chain = create_retrieval_chain(history_aware_retriever, question_answer_chain)

    llm_response = chain.invoke({"input": chat_message, "chat_history": st.session_state.chat_history})
    # 会話履歴を追加
    st.session_state.chat_history.extend([HumanMessage(content=chat_message), llm_response["answer"]])

    return llm_response
