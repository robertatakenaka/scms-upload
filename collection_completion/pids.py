"""
PIDs da plataforma clássica, que são por coleção:

- periódico: ISSN escolhido para a coleção (issn_scielo), 9 caracteres
  Ex.: 0103-6564
- fascículo: PID do periódico + ano + ordem do fascículo (4 dígitos),
  17 caracteres. Ex.: 0103-656420090003
- artigo (pid v2): S + PID do fascículo + ordem do artigo (5 dígitos),
  23 caracteres. Ex.: S0103-65642009000300003

O mesmo periódico pode ter PIDs diferentes em cada coleção (ex.: Psicologia
USP: 0103-6564 em scl e 1678-5177 em psi) e, consequentemente, fascículos e
artigos também. Ao completar a coleção destino, os PIDs são construídos com o
PID do periódico na coleção destino, mantendo o ano e as ordens da origem.
"""

JOURNAL_PID_LENGTH = 9
ISSUE_PID_LENGTH = 17
ARTICLE_PID_LENGTH = 23
ISSUE_ORDER_LENGTH = 4
ARTICLE_ORDER_LENGTH = 5


def is_valid_journal_pid(journal_pid):
    return bool(journal_pid) and len(journal_pid) == JOURNAL_PID_LENGTH


def is_valid_issue_pid(issue_pid):
    return bool(issue_pid) and len(issue_pid) == ISSUE_PID_LENGTH


def is_valid_article_pid(article_pid):
    return (
        bool(article_pid)
        and len(article_pid) == ARTICLE_PID_LENGTH
        and article_pid[0].upper() == "S"
    )


def get_issue_order(issue_pid):
    """
    Ordem do fascículo contida no PID do fascículo
    Ex.: 0103-656420090003 -> 0003
    """
    if is_valid_issue_pid(issue_pid):
        return issue_pid[-ISSUE_ORDER_LENGTH:]
    return None


def get_article_order(article_pid):
    """
    Ordem do artigo contida no pid v2
    Ex.: S0103-65642009000300003 -> 00003
    """
    if is_valid_article_pid(article_pid):
        return article_pid[-ARTICLE_ORDER_LENGTH:]
    return None


def get_issue_pid_from_article_pid(article_pid):
    """
    PID do fascículo contido no pid v2
    Ex.: S0103-65642009000300003 -> 0103-656420090003
    """
    if is_valid_article_pid(article_pid):
        return article_pid[1 : 1 + ISSUE_PID_LENGTH]
    return None


def build_issue_pid(journal_pid, year, issue_order):
    """
    PID do fascículo: PID do periódico + ano + ordem do fascículo

    Returns
    -------
    str or None
        None se algum dos dados é inválido
    """
    year = str(year or "")
    issue_order = str(issue_order or "")
    if issue_order.isdigit():
        issue_order = issue_order.zfill(ISSUE_ORDER_LENGTH)
    if not is_valid_journal_pid(journal_pid):
        return None
    if not (len(year) == 4 and year.isdigit()):
        return None
    if not (len(issue_order) == ISSUE_ORDER_LENGTH and issue_order.isdigit()):
        return None
    return f"{journal_pid}{year}{issue_order}"


def build_article_pid(issue_pid, source_article_pid):
    """
    pid v2 do artigo na coleção destino: S + PID do fascículo na coleção
    destino + ordem do artigo na coleção origem

    Returns
    -------
    str or None
        None se algum dos dados é inválido
    """
    article_order = get_article_order(source_article_pid)
    if not article_order or not is_valid_issue_pid(issue_pid):
        return None
    return f"S{issue_pid}{article_order}"


def belongs_to_issue(article_pid, issue_pid):
    """
    Indica se o pid v2 é de artigo do fascículo
    """
    return bool(issue_pid) and get_issue_pid_from_article_pid(article_pid) == issue_pid
