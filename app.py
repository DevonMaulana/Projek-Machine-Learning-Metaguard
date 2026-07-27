"""MetaGuard Streamlit entry point."""

import streamlit as st


def main() -> None:
    """Render the initial MetaGuard application page."""
    st.set_page_config(
        page_title="MetaGuard",
        page_icon="??",
        layout="wide",
    )

    st.title("MetaGuard")
    st.write(
        "Prototipe validasi kualitas dataset dan metadata OPD."
    )
    st.info("Repository berhasil diinisialisasi.")


if __name__ == "__main__":
    main()
