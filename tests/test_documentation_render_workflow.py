"""Guard the opt-in documentation publishing workflow contract."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


class DocumentationRenderWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.render = (WORKFLOWS / "documentation-render.yml").read_text(encoding="utf-8")
        cls.regression = (WORKFLOWS / "regression.yml").read_text(encoding="utf-8")

    def test_manual_only_and_branch_guarded(self):
        self.assertIn("  workflow_dispatch:", self.render)
        self.assertNotIn("  push:", self.render)
        self.assertNotIn("  pull_request:", self.render)
        self.assertIn("if: github.ref_type == 'branch'", self.render)
        self.assertIn("documentation-render-${{ github.ref }}", self.render)

    def test_push_uses_same_selected_branch_and_app_token(self):
        self.assertIn("actions/create-github-app-token@v2", self.render)
        self.assertIn("token: ${{ steps.app-token.outputs.token }}", self.render)
        self.assertIn("ref: ${{ github.ref }}", self.render)
        self.assertIn('git push origin "HEAD:refs/heads/${GITHUB_REF_NAME}"', self.render)
        self.assertNotIn("push --force", self.render)

    def test_ssh_signed_commit_with_stable_message_and_noop(self):
        self.assertIn("SIGNING_KEY: ${{ secrets.COMMIT_SIGNING_KEY }}", self.render)
        self.assertIn("git config --local gpg.format ssh", self.render)
        self.assertIn("git commit -S -m 'docs(screenshots): refresh generated UI captures'", self.render)
        self.assertIn("if git diff --cached --quiet; then", self.render)
        self.assertIn("git add -A -- docs/assets/ docs/screenshots.md docs/screenshots_TR.md", self.render)

    def test_regression_does_not_render_or_upload(self):
        self.assertIn("      - name: Run regression suite", self.regression)
        self.assertIn("      - name: Report traced Maintenance allocations", self.regression)
        self.assertNotIn("render_docs_screenshots.py", self.regression)
        self.assertNotIn("actions/upload-artifact", self.regression)
        self.assertIn("tools/render_docs_screenshots.py", self.render)
        self.assertIn("tools/render_docs_workflows.py", self.render)
        self.assertIn("actions/upload-artifact@v4", self.render)


if __name__ == "__main__":
    unittest.main()
