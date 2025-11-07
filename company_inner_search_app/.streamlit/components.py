"""
このファイルは、画面表示に特化した関数定義のファイルです。
"""

############################################################
# ライブラリの読み込み
############################################################
from pathlib import Path
import streamlit as st
import utils
import constants as ct


############################################################
# 内部ユーティリティ（PDFページ番号の体裁）
############################################################
def _fmt_with_page_if_pdf(path: str, page: int | None) -> str:
    suffix = Path(str(path)).suffix.lower()
    if suffix == ".pdf" and isinstance(page, int):
        return f"{path}（p.{page + 1}）"  # 0始まりを 1 始まりに
    return str(path)


############################################################
# 画面系関数
############################################################
def display_app_title():
    st.title(ct.APP_NAME)
    st.caption("社内文書を横断検索 & 問い合わせ対応")


def display_select_mode():
    with st.sidebar:
        st.header("利用目的")
        st.radio(
            "モードを選択",
            [ct.ANSWER_MODE_1, ct.ANSWER_MODE_2],
            key="mode"
        )
        st.divider()
        st.markdown("**使い方**\n- 画面下のチャット欄に質問\n- Enterで送信")


def display_initial_ai_message():
    if "messages" not in st.session_state or not st.session_state.messages:
        with st.chat_message("assistant"):
            st.markdown(
                "こんにちは！\n\n- **社内文書検索**: 関連資料の場所を提示します\n"
                "- **社内問い合わせ**: 資料を根拠に回答します"
            )
            st.markdown("**入力例**")
            st.code("社員の育成方針に関するMTGの議事録\n人事部に所属している従業員情報を一覧化して", wrap_lines=True, language=None)


def display_conversation_log():
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            # ユーザー発話はそのまま
            if m["role"] == "user":
                st.markdown(m["content"])
                continue

            # アシスタント発話（モード分岐）
            if m["content"]["mode"] == ct.ANSWER_MODE_1:
                _render_search_message(m["content"])
            else:
                _render_contact_message(m["content"])


def _render_search_message(content: dict):
    # 検索ヒットなし
    if "no_file_path_flg" in content:
        st.markdown(content["answer"])
        return

    # メイン
    st.markdown(content["main_message"])
    icon = utils.get_source_icon(content["main_file_path"])
    main_path = content["main_file_path"]
    main_page = content.get("main_page_number")  # 0始まりを想定
    st.success(_fmt_with_page_if_pdf(main_path, main_page), icon=icon)

    # サブ
    if "sub_choices" in content and content["sub_choices"]:
        st.markdown(content["sub_message"])
        for sub in content["sub_choices"]:
            icon = utils.get_source_icon(sub["source"])
            st.info(_fmt_with_page_if_pdf(sub["source"], sub.get("page_number")), icon=icon)


def _render_contact_message(content: dict):
    st.markdown(content["answer"])
    if "file_info_list" in content:
        st.divider()
        st.markdown(f"##### {content['message']}")
        for file_info in content["file_info_list"]:
            icon = utils.get_source_icon(file_info)
            st.info(file_info, icon=icon)


def display_search_llm_response(llm_response):
    """
    「社内文書検索」モードのLLMレスポンス → 画面表示 & ログ用辞書を返却
    """
    if llm_response["context"] and llm_response["answer"] != ct.NO_DOC_MATCH_ANSWER:
        # メイン
        main_doc = llm_response["context"][0]
        main_file_path = main_doc.metadata.get("source", "")
        main_page_number = main_doc.metadata.get("page") if "page" in main_doc.metadata else None

        main_message = "入力内容に関する情報は、以下のファイルに含まれている可能性があります。"
        st.markdown(main_message)
        icon = utils.get_source_icon(main_file_path)
        st.success(_fmt_with_page_if_pdf(main_file_path, main_page_number), icon=icon)

        # サブ
        sub_choices = []
        sub_message = "その他、ファイルありかの候補を提示します。"
        shown = set([main_file_path])
        for doc in llm_response["context"][1:]:
            fp = doc.metadata.get("source", "")
            if not fp or fp in shown:
                continue
            shown.add(fp)
            page = doc.metadata.get("page") if "page" in doc.metadata else None
            sub_choices.append({"source": fp, "page_number": page})

        if sub_choices:
            st.markdown(sub_message)
            for sub in sub_choices:
                icon = utils.get_source_icon(sub["source"])
                st.info(_fmt_with_page_if_pdf(sub["source"], sub.get("page_number")), icon=icon)

        # 画面再描画用の内容（main.pyが messages に積む）
        content = {
            "mode": ct.ANSWER_MODE_1,
            "main_message": main_message,
            "main_file_path": main_file_path
        }
        if main_page_number is not None:
            content["main_page_number"] = main_page_number
        if sub_choices:
            content["sub_message"] = sub_message
            content["sub_choices"] = sub_choices
        return content

    # ヒットなし
    st.markdown(ct.NO_DOC_MATCH_MESSAGE)
    return {
        "mode": ct.ANSWER_MODE_1,
        "answer": ct.NO_DOC_MATCH_MESSAGE,
        "no_file_path_flg": True
    }


def display_contact_llm_response(llm_response):
    """
    「社内問い合わせ」モードのLLMレスポンス → 画面表示 & ログ用辞書を返却
    """
    st.markdown(llm_response["answer"])

    file_info_list = []
    if llm_response["answer"] != ct.INQUIRY_NO_MATCH_ANSWER:
        st.divider()
        message = "情報源"
        st.markdown(f"##### {message}")

        seen = set()
        for doc in llm_response["context"]:
            fp = doc.metadata.get("source", "")
            if not fp or fp in seen:
                continue
            seen.add(fp)
            page = doc.metadata.get("page") if "page" in doc.metadata else None
            formatted = _fmt_with_page_if_pdf(fp, page)
            icon = utils.get_source_icon(fp)
            st.info(formatted, icon=icon)
            file_info_list.append(formatted)

        content = {
            "mode": ct.ANSWER_MODE_2,
            "answer": llm_response["answer"],
            "message": message,
            "file_info_list": file_info_list
        }
    else:
        content = {
            "mode": ct.ANSWER_MODE_2,
            "answer": llm_response["answer"]
        }

    return content
