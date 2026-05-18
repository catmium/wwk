# """
# Persistent Streamlit widget wrappers.

# Each wrapper keeps st.session_state["draft"] (single source of truth) in sync
# with the widget's internal buffer so values survive reruns and page switches.

# Depends on state.py for draft/buffer primitives.
# """
# import streamlit as st

# from state import (
#     _widget_key,
#     ensure_widget_buffer,
#     on_widget_change,
#     draft_get,
#     draft_set,
#     set_field_value,
# )


# def p_text_input(label, field, default="", **kwargs):
#     ensure_widget_buffer(field, default)
#     st.text_input(
#         label,
#         key=_widget_key(field),
#         on_change=on_widget_change,
#         args=(field, str),
#         **kwargs,
#     )
#     return draft_get(field, default)


# def p_text_area(label, field, default="", **kwargs):
#     ensure_widget_buffer(field, default)
#     st.text_area(
#         label,
#         key=_widget_key(field),
#         on_change=on_widget_change,
#         args=(field, str),
#         **kwargs,
#     )
#     return draft_get(field, default)


# def p_number_input(label, field, default, cast=None, **kwargs):
#     ensure_widget_buffer(field, default)
#     st.number_input(
#         label,
#         key=_widget_key(field),
#         on_change=on_widget_change,
#         args=(field, cast),
#         **kwargs,
#     )
#     return draft_get(field, default)


# def p_selectbox(label, field, options, default, format_func=None,
#                 on_change_extra=None, on_change_extra_args=(), **kwargs):
#     if draft_get(field, default) not in options:
#         draft_set(field, default)

#     ensure_widget_buffer(field, default)

#     current_value = draft_get(field, default)
#     if current_value not in options:
#         current_value = default
#         set_field_value(field, default)

#     index = options.index(current_value)

#     if on_change_extra is None:
#         change_handler = on_widget_change
#         change_args = (field, None)
#     else:
#         def _combined(_field=field, _extra=on_change_extra, _eargs=tuple(on_change_extra_args)):
#             on_widget_change(_field, None)
#             _extra(*_eargs)
#         change_handler = _combined
#         change_args = ()

#     selectbox_kwargs = dict(
#         label=label,
#         options=options,
#         index=index,
#         key=_widget_key(field),
#         on_change=change_handler,
#         args=change_args,
#         **kwargs,
#     )
#     if format_func is not None:
#         selectbox_kwargs["format_func"] = format_func

#     st.selectbox(**selectbox_kwargs)
    
#     return draft_get(field, default)


# def p_checkbox(label, field, default=False, **kwargs):
#     ensure_widget_buffer(field, default)
#     st.checkbox(
#         label,
#         key=_widget_key(field),
#         on_change=on_widget_change,
#         args=(field, bool),
#         **kwargs,
#     )
#     return draft_get(field, default)


# def p_date_input(label, field, default, **kwargs):
#     ensure_widget_buffer(field, default)
#     st.date_input(
#         label,
#         key=_widget_key(field),
#         on_change=on_widget_change,
#         args=(field, None),
#         **kwargs,
#     )
#     return draft_get(field, default)


# def p_percent_input(label, field, default_decimal, **kwargs):
#     """
#     Display a decimal rate (e.g. 0.03) as a percentage (3.0) in the widget.
#     Draft stores decimal; widget shows percent. Converts on change.
#     """
#     pct_field = f"{field}__pct_display"
#     wkey = _widget_key(pct_field)

#     decimal_val = draft_get(field, default_decimal)
#     if wkey not in st.session_state:
#         st.session_state[wkey] = round(float(decimal_val) * 100, 4)

#     def _on_pct_change():
#         pct_val = st.session_state[wkey]
#         draft_set(field, round(float(pct_val) / 100, 8))

#     st.number_input(label, key=wkey, on_change=_on_pct_change, **kwargs)
#     return draft_get(field, default_decimal)
"""
Persistent Streamlit widget wrappers.

Each wrapper keeps st.session_state["draft"] (single source of truth) in sync
with the widget's internal buffer so values survive reruns and page switches.

Depends on state.py for draft/buffer primitives.
"""
import streamlit as st

from state import (
    _widget_key,
    ensure_widget_buffer,
    on_widget_change,
    draft_get,
    draft_set,
    set_field_value,
)


def p_text_input(label, field, default="", **kwargs):
    ensure_widget_buffer(field, default)
    st.text_input(
        label,
        key=_widget_key(field),
        on_change=on_widget_change,
        args=(field, str),
        **kwargs,
    )
    return draft_get(field, default)


def p_text_area(label, field, default="", **kwargs):
    ensure_widget_buffer(field, default)
    st.text_area(
        label,
        key=_widget_key(field),
        on_change=on_widget_change,
        args=(field, str),
        **kwargs,
    )
    return draft_get(field, default)


def p_number_input(label, field, default, cast=None, **kwargs):
    ensure_widget_buffer(field, default)
    st.number_input(
        label,
        key=_widget_key(field),
        on_change=on_widget_change,
        args=(field, cast),
        **kwargs,
    )
    return draft_get(field, default)


def p_selectbox(label, field, options, default, format_func=None,
                on_change_extra=None, on_change_extra_args=(), **kwargs):
    if draft_get(field, default) not in options:
        draft_set(field, default)

    ensure_widget_buffer(field, default)

    current_value = draft_get(field, default)
    if current_value not in options:
        current_value = default
        set_field_value(field, default)

    if on_change_extra is None:
        change_handler = on_widget_change
        change_args = (field, None)
    else:
        def _combined(_field=field, _extra=on_change_extra, _eargs=tuple(on_change_extra_args)):
            on_widget_change(_field, None)
            _extra(*_eargs)
        change_handler = _combined
        change_args = ()

    wkey = _widget_key(field)

    selectbox_kwargs = dict(
        label=label,
        options=options,
        key=wkey,
        on_change=change_handler,
        args=change_args,
        **kwargs,
    )
    if format_func is not None:
        selectbox_kwargs["format_func"] = format_func

    # Only pass `index` when the key is NOT yet in session_state
    # (Streamlit forbids default + session-state-managed key simultaneously)
    if wkey not in st.session_state:
        selectbox_kwargs["index"] = options.index(current_value)

    st.selectbox(**selectbox_kwargs)
    return draft_get(field, default)


def p_checkbox(label, field, default=False, **kwargs):
    ensure_widget_buffer(field, default)
    st.checkbox(
        label,
        key=_widget_key(field),
        on_change=on_widget_change,
        args=(field, bool),
        **kwargs,
    )
    return draft_get(field, default)


def p_date_input(label, field, default, **kwargs):
    ensure_widget_buffer(field, default)
    st.date_input(
        label,
        key=_widget_key(field),
        on_change=on_widget_change,
        args=(field, None),
        **kwargs,
    )
    return draft_get(field, default)


def p_percent_input(label, field, default_decimal, **kwargs):
    """
    Display a decimal rate (e.g. 0.03) as a percentage (3.0) in the widget.
    Draft stores decimal; widget shows percent. Converts on change.
    """
    pct_field = f"{field}__pct_display"
    wkey = _widget_key(pct_field)

    decimal_val = draft_get(field, default_decimal)
    if wkey not in st.session_state:
        st.session_state[wkey] = round(float(decimal_val) * 100, 4)

    def _on_pct_change():
        pct_val = st.session_state[wkey]
        draft_set(field, round(float(pct_val) / 100, 8))

    st.number_input(label, key=wkey, on_change=_on_pct_change, **kwargs)
    return draft_get(field, default_decimal)