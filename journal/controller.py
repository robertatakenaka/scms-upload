import logging

from django.utils.translation import gettext_lazy as _

from journal.models import Journal

from . import exceptions


# def get_updated_official_journal(
#         user,
#         title, issn_l, e_issn, print_issn,
#         short_title,
#         foundation_date,
#         foundation_year,
#         foundation_month,
#         foundation_day,
#         ):
#     try:
#         # cria ou obtém official_journal
#         official_journal = OfficialJournal.get_or_create(
#             title, issn_l, e_issn, print_issn, user,
#         )
#         official_journal.update(
#             user,
#             short_title,
#             foundation_date,
#             foundation_year,
#             foundation_month,
#             foundation_day,
#         )
#         return official_journal
#     except Exception as e:
#         raise exceptions.GetUpdatedOfficialJournalError(
#             _('Unable to get or create official journal {} {} {} {} {} {}').format(
#                 title, issn_l, e_issn, print_issn, type(e), e
#             )
#         )

def get_journal_dict_for_validation(journal_id):
    data = {}

    try:
        journal = Journal.objects.get(pk=journal_id)
        titles = [
            journal.official_journal.title,
            journal.official_journal.short_title,
            journal.short_title,
            journal.nlm_title,
        ]
        # FIXME os títulos retornados deveria estar associados com sua
        # categoria correspondente (principal, short title iso, ...),
        # não deveria ser uma lista, mas sim um dicionário
        data['titles'] = [t for t in titles if t is not None and len(t) > 0]
        data['print_issn'] = journal.ISSN_print
        data['electronic_issn'] = journal.ISSN_electronic

    except OfficialJournal.DoesNotExist:
        ...

    return data
