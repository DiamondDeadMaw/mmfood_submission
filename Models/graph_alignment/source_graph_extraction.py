from Models.graph_alignment.metadata_extraction import extract_metadata
from Models.graph_alignment.section_text import get_sections


def extract_data_fast(full_text):
    sections = get_sections(full_text)
    return {"metadata": extract_metadata(sections["metadata"])}
