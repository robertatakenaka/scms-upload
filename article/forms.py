from wagtail.admin.forms import WagtailAdminModelForm


class ArticleForm(WagtailAdminModelForm):
    def save_all(self, user):
        article = super().save(commit=False)
        article.creator = user

        for dwl in article.doi_with_lang.all():
            dwl.creator = user

        for a in article.author.all():
            a.creator = user

        for t in article.title_with_lang.all():
            t.creator = user

        self.save()

        return article


class RelatedItemForm(WagtailAdminModelForm):
    def save_all(self, user):
        related_item = super().save(commit=False)
        related_item.creator = user

        self.save()

        return related_item


class RequestArticleChangeForm(WagtailAdminModelForm):
    def save_all(self, user, article):
        request_article_change = super().save(commit=False)
        request_article_change.creator = user
        request_article_change.article = article

        self.save()

        return request_article_change


class ScheduledArticleModelForm(WagtailAdminModelForm):

    def save_all(self, user):
        article = super().save(commit=False)

        if self.instance.pk is not None:
            article.updated_by = user
        else:
            article.creator = user

        self.save()

        return article
