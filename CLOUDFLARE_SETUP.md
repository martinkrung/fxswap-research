# Cloudflare Pages Deployment Setup

To enable automated plot generation and deployment to Cloudflare Pages, follow these steps:

## 1. Cloudflare Configuration

1. **Create a Cloudflare Pages Project**:
   - Go to your Cloudflare Dashboard -> **Workers & Pages**.
   - Click **Create application** -> **Pages** -> **Upload assets**.
   - Note down the **Project Name** (e.g., `fxswap-research`).

2. **Get your Account ID**:
   - On the Cloudflare Dashboard, your **Account ID** is visible in the URL or on the right sidebar of your Account Home page.

3. **Generate an API Token**:
   - Go to **My Profile** -> **API Tokens**.
   - Click **Create Token**.
   - Use the **Cloudflare Pages** template or create a custom token with:
     - Account -> Cloudflare Pages -> Edit
   - Note down the token.

## 2. GitHub Secrets

Add the following secrets to your GitHub repository (**Settings** -> **Secrets and variables** -> **Actions** -> **New repository secret**):

- `CLOUDFLARE_API_TOKEN`: The API token you generated.
- `CLOUDFLARE_ACCOUNT_ID`: Your Cloudflare Account ID.
- `CLOUDFLARE_PROJECT_NAME`: The name of your Cloudflare Pages project.

## 3. Automation Details

The workflow `.github/workflows/deploy-cloudflare.yml` is configured to:
1. Run automatically after the "Collect FXSwap Data Hourly" workflow completes successfully.
2. Generate all weekly plots and HTML index pages.
3. Deploy the `plots/` directory directly to Cloudflare Pages.

This setup ensures your website is always up to date with the latest data without needing to store every PNG version in your git history (though current ones are kept for local preview).
