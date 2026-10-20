"""Recipes: manage recipes and their immutable-once-used revisions."""

import bootstrap  # noqa: F401  # isort: skip

import streamlit as st

from textile_dyeing_intelligence import constants as c
from textile_dyeing_intelligence import ui
from textile_dyeing_intelligence.errors import TDIError, ValidationFailure
from textile_dyeing_intelligence.services import materials as materials_service
from textile_dyeing_intelligence.services import recipes as svc

COLS = ["Material", "Quantity", "Unit", "Dosing basis", "Notes"]


def _frame(ingredients: list[dict] | None) -> list[dict]:
    if ingredients:
        return [
            {
                "Material": i["material_name"],
                "Quantity": i["quantity"],
                "Unit": i["unit"],
                "Dosing basis": i["dosing_basis"] or "",
                "Notes": i["notes"] or "",
            }
            for i in ingredients
        ]
    return [{k: "" for k in COLS}]


def _ingredients(edited) -> list[dict]:
    rows = edited if isinstance(edited, list) else edited.to_dict("records")
    out = []
    for r in rows:
        values = {k: ("" if r.get(k) is None else str(r.get(k)).strip()) for k in COLS}
        if not any(values.values()):
            continue
        out.append(
            {
                "material_name": values["Material"],
                "quantity": values["Quantity"],
                "unit": values["Unit"],
                "dosing_basis": values["Dosing basis"],
                "notes": values["Notes"],
            }
        )
    return out


def ingredient_editor(key: str, seed: list[dict] | None, conn):
    known = [m["name"] for m in materials_service.list_materials(conn)]
    if known:
        st.caption(
            "Known materials: "
            + ", ".join(known[:30])
            + (" ..." if len(known) > 30 else "")
            + ". A new name creates a new catalogue entry."
        )
    st.caption(
        "One row per ingredient. Quantity must be greater than zero; enter a unit for every row. "
        "Recipe data is recorded as entered and is not validated dyeing guidance."
    )
    return st.data_editor(
        _frame(seed),
        num_rows="dynamic",
        hide_index=True,
        key=key,
        width="stretch",
        column_config={c_: st.column_config.TextColumn(c_) for c_ in COLS},
    )


def revision_form(conn, name: str, recipe_id: int | None, seed: list[dict] | None = None) -> None:
    """Create a recipe (recipe_id None) or a new revision of an existing recipe."""
    fk = ui.form_key(name)
    top = st.container()
    slots = ui.Slots()
    with st.form(fk):
        if recipe_id is None:
            st.markdown("**Recipe identity**")
            rcode = st.text_input(ui.req("Recipe identifier"), key=f"{fk}_rcode", max_chars=40)
            slots.after("recipe_code")
            rname = st.text_input(ui.req("Recipe name"), key=f"{fk}_rname", max_chars=200)
            slots.after("name")
            rdesc = st.text_area("Description or intended application (optional)", key=f"{fk}_rdesc")
            rmat = st.text_input("Applicable fabric or material (optional)", key=f"{fk}_rmat")
        st.markdown("**Revision**")
        rev_code = st.text_input(ui.req("Revision identifier"), key=f"{fk}_rev", max_chars=40, help="e.g. A, B, 2026-1")
        slots.after("revision_code")
        eff = st.date_input("Effective date (optional)", value=None, key=f"{fk}_eff")
        rev_desc = st.text_area("Revision notes (optional)", key=f"{fk}_revdesc")
        st.markdown("**Ingredients**")
        edited = ingredient_editor(f"{fk}_ing", seed, conn)
        slots.after("ingredients")
        submitted = st.form_submit_button("Save Revision" if recipe_id else "Create Recipe")
    if submitted:
        revision = {
            "revision_code": rev_code,
            "effective_date": ui.date_str(eff),
            "description": rev_desc,
            "ingredients": _ingredients(edited),
        }
        try:
            if recipe_id is None:
                recipe = {"recipe_code": rcode, "name": rname, "description": rdesc, "applicable_material": rmat}
                saved = svc.create_recipe(conn, recipe, revision)
                ui.saved(name, f"Recipe {saved['recipe_code']} revision {saved['revision_code']} created successfully.")
            else:
                saved = svc.add_revision(conn, recipe_id, revision)
                ui.saved(
                    name, f"Revision {saved['revision_code']} created successfully. Earlier revisions are unchanged."
                )
        except ValidationFailure as exc:
            ui.show_failure(top, slots, exc)
        except TDIError as exc:
            top.error(str(exc))


def body(conn) -> None:
    list_tab, add_tab = st.tabs(["Recipes and revisions", "New recipe"])
    with list_tab:
        cols = st.columns(2)
        search = cols[0].text_input("Search by identifier or name", key="r_search")
        status = cols[1].selectbox(
            "Status",
            [None, *c.RECIPE_STATUSES],
            key="r_status",
            format_func=lambda s: "All statuses" if s is None else c.RECIPE_STATUS_LABELS[s],
        )
        recipes = svc.list_recipes(conn, search or None, status)
        rows = [
            {
                "Recipe ID": r["recipe_code"],
                "Name": r["name"],
                "Applicable material": r["applicable_material"],
                "Status": ui.status_text(r["status"], c.RECIPE_STATUS_LABELS),
                "Revisions": r["revision_count"],
                "Created": r["created_at"][:10],
            }
            for r in recipes
        ]
        picked = ui.table(
            rows, key="recipe_table", selectable=True, empty="No recipes match. Use 'New recipe' to create one."
        )
        if picked is None:
            return
        recipe = recipes[picked]
        st.subheader(f"Recipe {recipe['recipe_code']} - {recipe['name']}")
        if recipe["description"]:
            st.write(recipe["description"])
        revisions = svc.list_revisions(conn, recipe["id"])
        ui.table(
            [
                {
                    "Revision": r["revision_code"],
                    "Status": ui.status_text(r["status"], c.RECIPE_STATUS_LABELS),
                    "Effective date": r["effective_date"],
                    "Created": r["created_at"][:10],
                    "Batches using it": r["batch_count"],
                    "Notes": r["description"],
                }
                for r in revisions
            ]
        )
        rev_ids = [r["id"] for r in revisions]
        chosen = st.selectbox(
            "View revision",
            rev_ids,
            index=len(rev_ids) - 1,
            key=f"viewrev_{recipe['id']}",
            format_func=lambda i: next(r["revision_code"] for r in revisions if r["id"] == i),
        )
        detail = svc.get_revision(conn, chosen)
        st.markdown(
            f"**Ingredients of revision {detail['revision_code']}** "
            f"(used by {detail['batch_count']} batch(es); revisions in use cannot be edited)"
        )
        ui.table(
            [
                {
                    "Material": i["material_name"],
                    "Quantity": i["quantity"],
                    "Unit": i["unit"],
                    "Dosing basis": i["dosing_basis"],
                    "Notes": i["notes"],
                }
                for i in detail["ingredients"]
            ]
        )
        with st.expander("Create a new revision (starts from the revision shown above)"):
            revision_form(conn, f"newrev_{recipe['id']}_{chosen}", recipe["id"], detail["ingredients"])
        with st.expander("Archive or reactivate"):
            st.caption(
                "Archiving stops the recipe being chosen for new batches. History and existing batches are unaffected."
            )
            target = "archived" if recipe["status"] == "active" else "active"
            if st.button(f"Set recipe {c.RECIPE_STATUS_LABELS[target].lower()}", key=f"rs_{recipe['id']}"):
                try:
                    svc.set_recipe_status(conn, recipe["id"], target)
                    ui.flash(f"Recipe {recipe['recipe_code']} is now {c.RECIPE_STATUS_LABELS[target].lower()}.")
                    st.rerun()
                except TDIError as exc:
                    st.error(str(exc))
            rev = svc.get_revision(conn, chosen)
            rtarget = "archived" if rev["status"] == "active" else "active"
            if st.button(
                f"Set revision {rev['revision_code']} {c.RECIPE_STATUS_LABELS[rtarget].lower()}", key=f"rvs_{chosen}"
            ):
                try:
                    svc.set_revision_status(conn, chosen, rtarget)
                    ui.flash(f"Revision {rev['revision_code']} is now {c.RECIPE_STATUS_LABELS[rtarget].lower()}.")
                    st.rerun()
                except TDIError as exc:
                    st.error(str(exc))
    with add_tab:
        revision_form(conn, "recipe_add", None)


ui.run_page("Recipes", "Manage recipes and their revisions. A revision used by a batch is never changed.", body)
