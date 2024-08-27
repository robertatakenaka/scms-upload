WAGTAIL_MENU_APPS_ORDER = [
    None,
    "upload",
    "article",
    "issue",
    "journal",
    "collection",
    "processing",
    "migration",
    "Tarefas",
    "unexpected-error",
    "pid_provider",
    "institution",
    "location",
    "researcher",
    "upload-error",
    "Configurações",
    "Relatórios",
    "Images",
    "Documentos",
    "Ajuda",
]


def get_menu_order(app_name):
    try:
        return WAGTAIL_MENU_APPS_ORDER.index(app_name)
    except:
        return 9000
