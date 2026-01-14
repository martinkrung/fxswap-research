# Plan: Update Plot Naming and HTML Width

## Goal
1. Update `plot_refule.py` naming convention to `week_YYYY_Www_YYYY-MM-DD.png`.
2. Update `html_generator.py` to show full-width images without cropping or scrollbars.

## Steps
1. **Modify `scripts/plot_refule.py`**:
    - Update `filename` logic to include the Monday date string.
2. **Modify `scripts/html_generator.py`**:
    - Remove `max-width` on the market page body.
    - Remove `overflow-x: auto` on `.plot-image-wrapper`.
    - Set `img` to `width: auto` and `max-width: none`.
3. **Verify**:
    - Run `python3 scripts/plot_refule.py --index 0 --force`.
    - Inspect file names and layout.
4. **Deploy**:
    - Run `python3 scripts/plot_refule.py --all`.
