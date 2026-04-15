from adam.state import AppState, Session


def _create_session(state: AppState) -> Session:
    session_id = state.next_session_id()
    session = Session(id=session_id)
    state.sessions[session_id] = session
    state.active_session_id = session_id
    return session


def get_or_create_active_session(state: AppState) -> Session:
    if state.active_session_id is not None:
        session = state.sessions.get(state.active_session_id)
        if session is not None:
            return session
    return _create_session(state)


def save_history(state: AppState, messages: list[dict]) -> None:
    session = get_or_create_active_session(state)
    session.messages = messages
