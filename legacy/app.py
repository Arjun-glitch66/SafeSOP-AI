
import re
import streamlit as st
from pathlib import Path

from src.database import (
    init_db,
    get_connection,
    save_evaluation,
    get_evaluations,
)
from src.document_parser import extract_pdf_pages
from src.version_manager import (
    register_uploaded_document,
    create_request,
    save_generated_version,
    list_document_versions,
)
from src.sop_generator import generate_sop
from src.safety_evaluator import evaluate_sop


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

st.set_page_config(
    page_title="SafeSOP AI",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()


# --------------------------------------------------
# SESSION STATE
# --------------------------------------------------

defaults = {
    "document": None,
    "pages": [],
    "source_text": "",
    "request_id": None,
    "change_request": "",
    "scope": "full",
    "target_page": None,
    "target_section": None,
    "draft": None,
    "evaluation": None,
    "feedback": "",
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# --------------------------------------------------
# PROFESSIONAL DARK THEME
# --------------------------------------------------

st.markdown("""
<style>
.stApp {
    background: #0b1020;
    color: #e7edf8;
}
.block-container {
    max-width: 1450px;
    padding-top: 1.8rem;
    padding-bottom: 3rem;
}
section[data-testid="stSidebar"] {
    background: #10182a;
    border-right: 1px solid #26344d;
}
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] label {
    color: #c6d1e5;
}
h1, h2, h3 {
    color: #f3f6ff !important;
    letter-spacing: -0.4px;
}
p, label {
    color: #c6d1e5;
}
div[data-testid="stMetric"] {
    background: #141f34;
    border: 1px solid #293b59;
    border-radius: 14px;
    padding: 18px;
}
div[data-testid="stMetricLabel"] {
    color: #9eafc9;
}
div[data-testid="stMetricValue"] {
    color: #f2f6ff;
}
.stButton > button {
    background: #3478f6;
    color: white;
    border: 1px solid #3478f6;
    border-radius: 9px;
    font-weight: 600;
    min-height: 42px;
}
.stButton > button:hover {
    background: #2563eb;
    border-color: #73a0ff;
    color: white;
}
.stTextInput input, .stTextArea textarea {
    background: #141f34;
    color: #f2f6ff;
    border-radius: 9px;
}
div[data-testid="stFileUploader"] {
    background: #141f34;
    border: 1px dashed #405779;
    border-radius: 14px;
    padding: 14px;
}
div[data-testid="stExpander"] {
    background: #111a2d;
    border: 1px solid #293854;
    border-radius: 12px;
}
div[data-testid="stDataFrame"] {
    border: 1px solid #293854;
    border-radius: 10px;
}
hr {
    border-color: #293854;
}
.sop-hero {
    background: linear-gradient(120deg, #142544, #111a2d);
    border: 1px solid #304669;
    padding: 28px;
    border-radius: 18px;
    margin-bottom: 22px;
}
.sop-hero h1 {
    margin-bottom: 8px;
}
.sop-muted {
    color: #9eafc9;
}
.sop-card {
    background: #141f34;
    border: 1px solid #293b59;
    border-radius: 14px;
    padding: 20px;
    min-height: 125px;
}
.sop-card h3 {
    font-size: 17px;
    margin-bottom: 8px;
}
.sop-card p {
    font-size: 13px;
    color: #9eafc9;
}
.sop-pill {
    display: inline-block;
    padding: 5px 10px;
    background: #1e3556;
    border: 1px solid #365b88;
    border-radius: 20px;
    color: #b9d5ff;
    font-size: 12px;
}
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------

def get_current_document():
    return st.session_state.document


def get_original_pages():
    return st.session_state.pages


def get_document_versions():
    doc = get_current_document()
    if not doc:
        return []
    return list_document_versions(doc["document_id"])


def extract_warning_candidates(text):
    """
    Preliminary heuristic only.
    These snippets are not authoritative safety labels.
    """
    pattern = re.compile(
        r".{0,100}\b("
        r"warning|danger|caution|must not|do not|"
        r"disconnect|emergency|protective equipment"
        r")\b.{0,150}",
        re.IGNORECASE,
    )
    return [
        match.group(0).strip()
        for match in pattern.finditer(text)
    ]


def get_source_for_draft(draft):
    scope = draft["scope"]

    if scope == "page":
        page_number = st.session_state.target_page
        pages = get_original_pages()

        if not page_number or page_number > len(pages):
            raise ValueError("The selected original page is unavailable.")

        return pages[page_number - 1]["text"]

    return st.session_state.source_text


def render_status(status):
    if status == "PASS":
        st.success("No failures detected by the configured checks.")
    else:
        st.error("Review required: one or more checks failed or need attention.")


# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------

with st.sidebar:
    st.markdown("## 🛡️ SafeSOP AI")
    st.caption("Safety-aware document intelligence")
    st.divider()

    page = st.radio(
        "WORKSPACE",
        [
            "Dashboard",
            "Document Workspace",
            "Change Request",
            "Generate & Regenerate",
            "Safety Evaluation",
            "Version History",
        ],
        label_visibility="visible",
    )

    st.divider()

    doc = get_current_document()

    if doc:
        st.markdown("**Active document**")
        st.caption(doc["original_name"])
        st.caption(f"Document ID: {doc['document_id']}")
    else:
        st.caption("No document loaded")

    st.divider()
    st.caption("AI-generated drafts require qualified human review.")


# --------------------------------------------------
# DASHBOARD
# --------------------------------------------------

if page == "Dashboard":
    st.markdown("""
    <div class="sop-hero">
        <span class="sop-pill">AI-POWERED DOCUMENT WORKSPACE</span>
        <h1>SafeSOP AI</h1>
        <p class="sop-muted">
        Generate revised SOP drafts, inspect changes, evaluate
        safety-critical requirements and manage document versions.
        </p>
    </div>
    """, unsafe_allow_html=True)

    doc = get_current_document()
    versions = get_document_versions() if doc else []

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Active documents",
        1 if doc else 0,
    )
    col2.metric(
        "Generated versions",
        len(versions),
    )
    col3.metric(
        "Original pages",
        len(get_original_pages()) if doc else 0,
    )
    col4.metric(
        "Saved evaluations",
        sum(len(get_evaluations(v["id"])) for v in versions),
    )

    st.markdown("## Workspace")

    cards = [
        (
            "📄 Document Workspace",
            "Upload a source SOP and inspect its pages.",
        ),
        (
            "✏️ Change Request",
            "Describe the process change and choose the output scope.",
        ),
        (
            "⚙️ Generate & Regenerate",
            "Create a new draft or try again with feedback.",
        ),
        (
            "🛡️ Safety Evaluation",
            "Inspect warning preservation and validation findings.",
        ),
        (
            "🕘 Version History",
            "Review previous drafts and saved evaluation results.",
        ),
    ]

    card_cols = st.columns(3)

    for index, (title, description) in enumerate(cards):
        with card_cols[index % 3]:
            st.markdown(
                f"""
                <div class="sop-card">
                    <h3>{title}</h3>
                    <p>{description}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("## Recent versions")

    if versions:
        st.dataframe(
            [
                {
                    "Version": v["version_name"],
                    "Status": v["status"],
                    "Created": v["created_at"],
                }
                for v in versions[-5:][::-1]
            ],
            use_container_width=True,
        )
    else:
        st.info("Upload an SOP to start your first revision.")

    if st.button("Open Document Workspace", type="primary"):
        st.session_state["go_to_workspace"] = True
        st.rerun()


# --------------------------------------------------
# DOCUMENT WORKSPACE
# --------------------------------------------------

elif page == "Document Workspace":
    st.title("Document Workspace")
    st.caption("Upload and inspect your immutable source document.")

    uploaded = st.file_uploader(
        "Upload original SOP",
        type=["pdf"],
        help="The original is stored separately from generated drafts.",
    )

    if uploaded:
        if st.button("Store original and inspect", type="primary"):
            try:
                uploaded.seek(0)

                doc = register_uploaded_document(uploaded)
                pages = extract_pdf_pages(doc["original_path"])

                if not pages:
                    st.error("This PDF contains no pages.")
                else:
                    st.session_state.document = doc
                    st.session_state.pages = pages
                    st.session_state.source_text = "\n\n".join(
                        f"PAGE {p['page_number']}\n{p['text']}"
                        for p in pages
                    )
                    st.session_state.request_id = None
                    st.session_state.change_request = ""
                    st.session_state.draft = None
                    st.session_state.evaluation = None

                    st.success("Original stored successfully.")
                    st.rerun()

            except Exception as exc:
                st.error(f"Upload failed: {exc}")

    doc = get_current_document()

    if doc:
        st.markdown("## Original document")

        a, b, c = st.columns(3)
        a.metric("Pages", len(get_original_pages()))
        b.metric(
            "Pages with text",
            sum(bool(p["text"]) for p in get_original_pages()),
        )
        c.metric(
            "Extracted characters",
            len(st.session_state.source_text),
        )

        st.write("**Filename:**", doc["original_name"])
        st.write("**SHA-256:**", doc["file_hash"])

        selected_page = st.selectbox(
            "Preview original page",
            range(1, len(get_original_pages()) + 1),
        )

        page_data = get_original_pages()[selected_page - 1]

        st.text_area(
            "Extracted page text",
            page_data["text"],
            height=320,
            disabled=True,
        )

        if not page_data["text"]:
            st.warning(
                "No text was extracted from this page. OCR may be required."
            )


# --------------------------------------------------
# CHANGE REQUEST
# --------------------------------------------------

elif page == "Change Request":
    st.title("Process Change Request")
    st.caption("Specify what changed and which content should be revised.")

    doc = get_current_document()

    if not doc:
        st.warning("Upload an original SOP first.")
    else:
        pages = get_original_pages()

        scope_label = st.radio(
            "Output scope",
            [
                "Full document",
                "Selected page",
                "Selected section",
                "Selected step",
            ],
        )

        scope_map = {
            "Full document": "full",
            "Selected page": "page",
            "Selected section": "section",
            "Selected step": "step",
        }

        scope = scope_map[scope_label]
        target_page = None
        target_section = None

        if scope == "page":
            target_page = st.selectbox(
                "Page to revise",
                range(1, len(pages) + 1),
            )

        if scope in ("section", "step"):
            target_section = st.text_input(
                "Section heading or step identifier"
            )

        if scope == "step":
            target_page = st.selectbox(
                "Page containing this step",
                range(1, len(pages) + 1),
            )

        change_request = st.text_area(
            "Engineer change request",
            height=160,
            placeholder=(
                "Describe the change, the reason, and what must remain "
                "unchanged. Avoid ambiguous instructions."
            ),
        )

        if st.button("Save request", type="primary"):
            if not change_request.strip():
                st.error("Enter the process change.")
            elif scope in ("section", "step") and not target_section:
                st.error("Enter the section or step identifier.")
            else:
                try:
                    request_id = create_request(
                        document_id=doc["document_id"],
                        change_request=change_request,
                        output_scope=scope,
                        target_page=target_page,
                        target_section=target_section,
                    )

                    st.session_state.request_id = request_id
                    st.session_state.change_request = change_request
                    st.session_state.scope = scope
                    st.session_state.target_page = target_page
                    st.session_state.target_section = target_section
                    st.session_state.draft = None
                    st.session_state.evaluation = None

                    st.success(f"Request saved. ID: {request_id}")

                except Exception as exc:
                    st.error(f"Could not save request: {exc}")


# --------------------------------------------------
# GENERATE AND REGENERATE
# --------------------------------------------------

elif page == "Generate & Regenerate":
    st.title("Generate & Regenerate")
    st.caption("Each successful generation creates a new saved draft.")

    doc = get_current_document()

    if not doc:
        st.warning("Upload an original SOP first.")
    elif not st.session_state.request_id:
        st.warning("Save a change request first.")
    else:
        versions = get_document_versions()

        if versions:
            st.markdown("### Existing drafts")

            st.dataframe(
                [
                    {
                        "Version": v["version_name"],
                        "Status": v["status"],
                        "Created": v["created_at"],
                    }
                    for v in versions
                ],
                use_container_width=True,
            )

        feedback = st.text_area(
            "Regeneration feedback",
            placeholder=(
                "Example: Preserve the warnings, shorten the explanation, "
                "and avoid changing unaffected steps."
            ),
            height=100,
        )

        if st.button("Generate new version", type="primary"):
            try:
                scope = st.session_state.scope
                pages = get_original_pages()
                target_page = st.session_state.target_page

                # Always use the immutable original as generation input.
                if scope == "page":
                    source_text = pages[target_page - 1]["text"]
                elif scope == "step":
                    source_text = pages[target_page - 1]["text"]
                else:
                    source_text = st.session_state.source_text

                if not source_text.strip():
                    st.error("The selected source contains no extracted text.")
                else:
                    with st.spinner("Generating with the configured LLM..."):
                        result = generate_sop(
                            original_text=source_text,
                            change_request=st.session_state.change_request,
                            output_scope=scope,
                            target_page=target_page,
                            target_section=st.session_state.target_section,
                            feedback=feedback.strip() or None,
                        )

                        saved = save_generated_version(
                            document_id=doc["document_id"],
                            request_id=st.session_state.request_id,
                            original_name=doc["original_name"],
                            generated_text=result["text"],
                            parent_version_id=None,
                        )

                    st.session_state.draft = {
                        **saved,
                        "text": result["text"],
                        "model": result["model"],
                        "input_tokens": result["input_tokens"],
                        "output_tokens": result["output_tokens"],
                        "scope": scope,
                    }
                    st.session_state.feedback = feedback
                    st.session_state.evaluation = None

                    st.success(f"Created {saved['version_name']}.")
                    st.rerun()

            except Exception as exc:
                st.error(
                    "Generation failed. Check your API credentials and "
                    f"model configuration. Details: {exc}"
                )

        draft = st.session_state.draft

        if draft:
            st.divider()
            st.markdown(f"## {draft['version_name']}")

            st.caption(f"Model: {draft['model']}")
            st.caption(
                f"Tokens: {draft['input_tokens']} input, "
                f"{draft['output_tokens']} output"
            )

            st.text_area(
                "Generated draft",
                draft["text"],
                height=400,
                disabled=True,
            )

            st.download_button(
                "Download editable draft",
                data=draft["text"],
                file_name=f"{draft['version_name']}.md",
                mime="text/markdown",
            )

            st.info(
                "The current output is editable Markdown/text. "
                "Layout-preserved PDF export is not implemented yet."
            )


# --------------------------------------------------
# SAFETY EVALUATION
# --------------------------------------------------

elif page == "Safety Evaluation":
    st.title("SAFE-SOP Safety Evaluation")
    st.caption("Review the generated draft against the original source.")

    doc = get_current_document()
    draft = st.session_state.draft

    if not doc or not draft:
        st.warning("Upload a source and generate a draft first.")
    else:
        st.warning(
            "This preliminary evaluator uses heuristic warning extraction "
            "and exact matching. It is not a safety certification."
        )

        if st.button("Evaluate selected draft", type="primary"):
            try:
                source_text = get_source_for_draft(draft)

                required_warnings = extract_warning_candidates(
                    source_text
                )
                generated_warnings = extract_warning_candidates(
                    draft["text"]
                )

                # Automatic step dependency extraction is not yet implemented.
                result = evaluate_sop(
                    required_warnings=required_warnings,
                    generated_warnings=generated_warnings,
                    instructions=[],
                    required_order_pairs=[],
                    generated_order=[],
                )

                # Never mark this heuristic-only result as safety-approved.
                save_evaluation(
                    document_id=doc["document_id"],
                    version_id=draft["version_id"],
                    metrics=result["metrics"],
                    findings=result["findings"],
                    status="REVIEW_REQUIRED",
                )

                st.session_state.evaluation = {
                    **result,
                    "version_id": draft["version_id"],
                }

            except Exception as exc:
                st.error(f"Evaluation failed: {exc}")

        result = st.session_state.evaluation

        if result:
            st.markdown("## Evaluation results")
            st.caption(f"Draft version ID: {result['version_id']}")

            metrics = result["metrics"]
            cols = st.columns(3)

            metric_labels = [
                ("warning_recall", "Warning Recall"),
                ("warning_precision", "Warning Precision"),
                (
                    "unsupported_instruction_rate",
                    "Unsupported Instruction Rate",
                ),
                (
                    "critical_order_integrity",
                    "Critical Order Integrity",
                ),
            ]

            for index, (key, label) in enumerate(metric_labels):
                value = metrics[key]
                cols[index % 3].metric(
                    label,
                    f"{value:.1%}",
                )

            render_status(result["status"])

            if result["findings"]:
                st.markdown("### Findings")

                for finding in result["findings"]:
                    with st.expander(
                        f"{finding['severity'].upper()} — "
                        f"{finding['type'].replace('_', ' ').title()}"
                    ):
                        st.json(finding["details"])
            else:
                st.info(
                    "No failures were detected by the configured checks. "
                    "This does not establish that the SOP is safe."
                )

            st.error(
                "Human review remains mandatory. This prototype does not "
                "infer step dependencies or independently verify every "
                "generated instruction."
            )


# --------------------------------------------------
# VERSION HISTORY
# --------------------------------------------------

elif page == "Version History":
    st.title("Version History")
    st.caption("Browse stored drafts and their evaluation records.")

    doc = get_current_document()

    if not doc:
        st.warning("Upload an original SOP first.")
    else:
        versions = list_document_versions(doc["document_id"])

        if not versions:
            st.info("No generated versions have been saved.")
        else:
            st.dataframe(
                [
                    {
                        "Version": v["version_name"],
                        "Number": v["version_number"],
                        "Status": v["status"],
                        "Created": v["created_at"],
                    }
                    for v in versions
                ],
                use_container_width=True,
            )

            version_names = {
                f"{v['version_name']} — {v['status']}": v
                for v in versions
            }

            selected_name = st.selectbox(
                "Select a version",
                list(version_names.keys()),
            )

            selected_version = version_names[selected_name]

            st.markdown("### Selected version")
            st.write("File:", selected_version["file_path"])
            st.write("Created:", selected_version["created_at"])

            file_path = Path(selected_version["file_path"])

            if file_path.is_file():
                st.download_button(
                    "Download selected version",
                    data=file_path.read_bytes(),
                    file_name=file_path.name,
                    key=f"download_version_{selected_version['id']}",
                )

            evaluations = get_evaluations(selected_version["id"])

            st.markdown("### Evaluation history")

            if not evaluations:
                st.info("No evaluation records for this version.")
            else:
                for index, evaluation in enumerate(evaluations):
                    with st.expander(
                        f"Evaluation {index + 1} — {evaluation['status']}"
                    ):
                        st.json({
                            "metrics": evaluation["metrics"],
                            "findings": evaluation["findings"],
                            "created_at": evaluation["created_at"],
                        })


# --------------------------------------------------
# FOOTER
# --------------------------------------------------

st.divider()
st.caption(
    "SafeSOP AI · AI-assisted drafting only · "
    "Generated procedures require qualified human approval."
)
