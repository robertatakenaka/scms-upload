from django.test import SimpleTestCase

from collection_completion.pids import (
    belongs_to_issue,
    build_article_pid,
    build_issue_pid,
    get_article_order,
    get_issue_order,
    get_issue_pid_from_article_pid,
)

# Psicologia USP: 0103-6564 em scl e 1678-5177 em psi
SCL_ISSUE_PID = "0103-656420090003"
PSI_ISSUE_PID = "1678-517720090003"
SCL_V2 = "S0103-65642009000300003"
PSI_V2 = "S1678-51772009000300003"


class BuildIssuePidTest(SimpleTestCase):
    def test_build_issue_pid(self):
        self.assertEqual(build_issue_pid("1678-5177", "2009", "0003"), PSI_ISSUE_PID)
        self.assertEqual(build_issue_pid("1678-5177", 2009, "3"), PSI_ISSUE_PID)

    def test_invalid_data(self):
        for args in (
            (None, "2009", "0003"),
            ("1678-517", "2009", "0003"),
            ("1678-5177", "09", "0003"),
            ("1678-5177", "2009", None),
            ("1678-5177", "2009", "00003"),
            ("1678-5177", "2009", "ab"),
        ):
            with self.subTest(args=args):
                self.assertIsNone(build_issue_pid(*args))


class BuildArticlePidTest(SimpleTestCase):
    def test_build_article_pid_keeps_the_article_order(self):
        self.assertEqual(build_article_pid(PSI_ISSUE_PID, SCL_V2), PSI_V2)

    def test_invalid_data(self):
        self.assertIsNone(build_article_pid(None, SCL_V2))
        self.assertIsNone(build_article_pid(PSI_ISSUE_PID, None))
        self.assertIsNone(build_article_pid(PSI_ISSUE_PID, "S0103-6564"))
        self.assertIsNone(build_article_pid("1678-5177", SCL_V2))


class PidPartsTest(SimpleTestCase):
    def test_get_issue_order(self):
        self.assertEqual(get_issue_order(SCL_ISSUE_PID), "0003")
        self.assertIsNone(get_issue_order("0103-6564"))

    def test_get_article_order(self):
        self.assertEqual(get_article_order(SCL_V2), "00003")
        self.assertIsNone(get_article_order(SCL_ISSUE_PID))

    def test_get_issue_pid_from_article_pid(self):
        self.assertEqual(get_issue_pid_from_article_pid(SCL_V2), SCL_ISSUE_PID)
        self.assertIsNone(get_issue_pid_from_article_pid(None))

    def test_belongs_to_issue(self):
        self.assertTrue(belongs_to_issue(SCL_V2, SCL_ISSUE_PID))
        self.assertFalse(belongs_to_issue(SCL_V2, PSI_ISSUE_PID))
        self.assertFalse(belongs_to_issue(SCL_V2, None))
