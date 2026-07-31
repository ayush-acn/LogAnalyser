from pathlib import Path
import json

import streamlit as st
import requests
from langchain_core.messages import HumanMessage, AIMessage

from frontend_utils import (
    ALL_FILES_OPTION,
    generate_thread_id,
    discover_log_files,
    thread_label,
)
from config import BACKEND_URL


st.set_page_config(page_title='Log Analyser Chat', page_icon=':mag:', layout='wide')


def init_session_state() -> None:
    if 'threads' not in st.session_state:
        st.session_state.threads = {}
    if 'thread_order' not in st.session_state:
        st.session_state.thread_order = []
    if 'current_thread_id' not in st.session_state:
        st.session_state.current_thread_id = None
    if 'draft_nonce' not in st.session_state:
        st.session_state.draft_nonce = 0


def start_new_chat_draft() -> None:
    st.session_state.current_thread_id = None
    st.session_state.draft_nonce += 1


def resolve_log_selection(selection: str, log_files: list[Path]) -> str:
    if selection == ALL_FILES_OPTION:
        return '\n'.join(str(path.resolve()) for path in log_files)
    return str(Path(selection).resolve())


def create_thread(mode: str, log_target: str) -> str:
    thread_id = generate_thread_id('query' if mode == 'Query' else 'scheduled')
    st.session_state.threads[thread_id] = {
        'mode': mode,
        'log_file': log_target,
        'messages': [],
        'label': None,
    }
    st.session_state.thread_order.insert(0, thread_id)
    st.session_state.current_thread_id = thread_id
    return thread_id


def render_sidebar() -> None:
    with st.sidebar:
        st.header('Log Analyser')

        if st.button('+ New Chat', use_container_width=True):
            start_new_chat_draft()

        st.divider()
        st.caption('Previous chats')

        if not st.session_state.thread_order:
            st.caption('No chats yet.')

        for thread_id in st.session_state.thread_order:
            thread = st.session_state.threads[thread_id]
            label = thread['label'] or thread_label(thread['mode'], None, thread_id)
            is_active = thread_id == st.session_state.current_thread_id
            if st.button(
                label,
                key=f'thread_btn_{thread_id}',
                use_container_width=True,
                type='primary' if is_active else 'secondary',
            ):
                st.session_state.current_thread_id = thread_id


def stream_backend_tokens(
    *,
    endpoint: str,
    payload: dict,
) -> object:
    """
    Generator of text chunks for st.write_stream, reading Flask SSE.
    """
    url = f"{BACKEND_URL.rstrip('/')}{endpoint}"
    with requests.post(url, json=payload, stream=True, timeout=600) as response:
        response.raise_for_status()
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            line = raw_line.strip()
            if not line.startswith('data:'):
                continue
            data = json.loads(line[5:].strip())
            event_type = data.get('type')
            if event_type == 'token' and data.get('text'):
                yield data['text']
            elif event_type == 'error':
                raise RuntimeError(data.get('message') or 'Backend analysis failed')
            elif event_type == 'done':
                break


def render_new_chat_form() -> None:
    st.subheader('Start a new analysis')
    nonce = st.session_state.draft_nonce

    mode = st.radio(
        'What would you like to do?',
        options=['Query', 'Scheduled Analyses'],
        horizontal=True,
        key=f'draft_mode_{nonce}',
    )

    user_query = None
    if mode == 'Query':
        user_query = st.text_input(
            'Your question about the logs',
            key=f'draft_query_{nonce}',
        )
    else:
        st.caption('No input needed - the agent will analyse the latest logs automatically.')

    folder_raw = st.text_input(
        'Absolute path to log folder',
        placeholder=r'C:\path\to\logs',
        key=f'draft_folder_{nonce}',
    )

    folder_path = Path(folder_raw.strip()) if folder_raw.strip() else None
    if not folder_path:
        st.caption('Enter an absolute folder path to list log files.')
        return

    if not folder_path.exists():
        st.error(f'Path does not exist: `{folder_path}`')
        return

    if not folder_path.is_dir():
        st.error(f'Path is not a folder: `{folder_path}`')
        return

    log_files = discover_log_files(folder_path)
    if not log_files:
        st.error(f'No log files found under `{folder_path}`.')
        return

    options = [ALL_FILES_OPTION, *[str(path.resolve()) for path in log_files]]
    selected = st.selectbox(
        'Log file to analyse',
        options=options,
        format_func=lambda value: (
            f'All files ({len(log_files)})'
            if value == ALL_FILES_OPTION
            else str(Path(value).relative_to(folder_path.resolve()))
        ),
        key=f'draft_file_{nonce}',
    )

    ready = selected is not None and (mode != 'Query' or bool((user_query or '').strip()))
    if mode == 'Query' and not ready:
        st.caption('Enter a question to enable the button.')

    if st.button('Start Analysis', type='primary', disabled=not ready):
        log_target = resolve_log_selection(selected, log_files)
        thread_id = create_thread(mode, log_target)
        run_turn(thread_id, user_query.strip() if user_query else None)
        st.rerun()


def render_message_history(messages) -> None:
    for message in messages:
        if isinstance(message, HumanMessage):
            st.chat_message('user').write(message.content)
        elif isinstance(message, AIMessage):
            st.chat_message('assistant').write(message.content)


def run_turn(thread_id: str, user_query: str | None) -> None:
    thread = st.session_state.threads[thread_id]
    messages = thread['messages']
    had_history_before = len(messages) > 0

    if thread['label'] is None:
        thread['label'] = thread_label(thread['mode'], user_query, thread_id)

    if user_query:
        st.chat_message('user').write(user_query)

    endpoint = '/query-analysis' if thread_id.startswith('query_') else '/scheduled-analysis'
    payload = {
        'log_file_path': thread['log_file'],
        'thread_id': thread_id,
    }
    if user_query:
        payload['user_query'] = user_query
    elif thread['mode'] == 'Query':
        payload['user_query'] = ''

    with st.chat_message('assistant'):
        try:
            response_text = st.write_stream(
                stream_backend_tokens(endpoint=endpoint, payload=payload)
            )
        except Exception as exc:
            response_text = (
                'The analysis failed while talking to the agent backend. '
                'This looks like a backend issue rather than a frontend one:\n\n'
                f'`{exc}`'
            )
            st.error(response_text)
        else:
            if not response_text:
                response_text = (
                    'The agent finished but streamed no text back. This likely points '
                    'to a backend issue rather than a frontend one.'
                )
                st.warning(response_text)

    if not had_history_before and not any(isinstance(m, HumanMessage) for m in messages):
        messages.append(HumanMessage(content=user_query or 'Please analyse the latest logs from the file.'))
    elif user_query and had_history_before:
        messages.append(HumanMessage(content=user_query))

    messages.append(AIMessage(content=response_text))


def render_active_chat() -> None:
    thread_id = st.session_state.current_thread_id
    thread = st.session_state.threads[thread_id]

    st.subheader('Chat')
    log_display = thread['log_file']
    if '\n' in log_display:
        file_count = len(log_display.splitlines())
        log_display = f'All files ({file_count})'
    st.caption(f"Mode: `{thread['mode']}` \u00b7 Log file: `{log_display}`")

    render_message_history(thread['messages'])

    follow_up = st.chat_input('Ask a follow-up question...')
    if follow_up:
        run_turn(thread_id, follow_up)
        st.rerun()


def main() -> None:
    init_session_state()
    render_sidebar()

    st.caption(f'Backend: `{BACKEND_URL}`')

    if st.session_state.current_thread_id is None:
        render_new_chat_form()
    else:
        render_active_chat()


if __name__ == '__main__':
    main()
