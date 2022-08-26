from defusedxml.ElementTree import parse
from defusedxml.ElementTree import tostring as defusedxml_tostring


def read_xml_file(file_path):
    return parse(file_path)


def tostring(xmltree):
    # garante que os diacríticos estarão devidamente representados
    return defusedxml_tostring(xmltree, encoding="utf-8").decod("utf-8")
