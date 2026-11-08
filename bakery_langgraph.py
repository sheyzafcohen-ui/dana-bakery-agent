"""Deterministic LangGraph workflow for Dana's Bakery orders.

Install dependencies with: pip install langgraph
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph


# Inventory is shared across invocations to represent the current day's stock.
INITIAL_INVENTORY: dict[str, int] = {
    "challah": 10,
    "sourdough": 4,
    "rugelach": 3,
    "babka": 0,
}
inventory: dict[str, int] = INITIAL_INVENTORY.copy()

PRICES: dict[str, float] = {
    "challah": 18.0,
    "babka": 45.0,
    "rugelach": 30.0,
    "sourdough": 25.0,
}
SUBSTITUTION_ORDER = ["babka", "rugelach", "sourdough", "challah"]
DISPLAY_NAMES = {
    "challah": "חלה",
    "babka": "בבקה",
    "rugelach": "רוגלך",
    "sourdough": "לחם מחמצת",
}


class OrderState(TypedDict, total=False):
    """The graph state. These are the only state keys used by the graph."""

    item: str
    quantity: int
    day: str
    city: str
    status: str
    delivery: str
    total: float
    message: str
    steps: list[str]
    rejections_count: int


def _steps(state: OrderState) -> list[str]:
    return list(state.get("steps", []))


def validate_order(state: OrderState) -> dict:
    steps = _steps(state)
    item = state.get("item")
    day = state.get("day")
    quantity = state.get("quantity")
    if (
        not isinstance(quantity, int)
        or isinstance(quantity, bool)
        or quantity < 1
        or not isinstance(item, str)
        or not item.strip()
        or not isinstance(day, str)
        or not day.strip()
    ):
        steps.append("Validation failed: missing fields or invalid quantity")
        return {
            "status": "rejected",
            "steps": steps,
            "message": "מצטערים, לא הצלחנו להבין את ההזמנה. אפשר לשלוח אותה שוב עם מוצר, כמות ויום תקינים?",
        }

    normalized_item = item.strip().lower()
    if normalized_item not in PRICES:
        steps.append("Validation failed: unsupported item")
        return {
            "status": "rejected",
            "steps": steps,
            "message": "מצטערים, לא הצלחנו לזהות את המאפה שביקשת. נשמח לקבל הזמנה עם אחד המאפים שבתפריט.",
        }

    steps.append("Order validated successfully")
    return {"item": normalized_item, "steps": steps, "rejections_count": 0}


def route_after_validation(state: OrderState) -> str:
    return END if state.get("status") == "rejected" else "check_shipping"


def check_shipping(state: OrderState) -> dict:
    city = state.get("city")
    steps = _steps(state)
    if city is None or not str(city).strip():
        delivery = "pickup"
        shipping_cost = 0.0
        steps.append("No city provided, set to pickup (free)")
    elif city == "Jerusalem":
        delivery = "delivery"
        shipping_cost = 20.0
        steps.append("Delivery to Jerusalem set (20 ILS)")
    else:
        delivery = "pickup"
        shipping_cost = 0.0
        steps.append(
            "City outside Jerusalem, automatically changed to pickup (free) and customer notified"
        )
    # Shipping cost is held privately in the state under no extra key: derive it
    # from the delivery method at pricing time (Jerusalem delivery costs 20 ILS).
    return {"delivery": delivery, "steps": steps}


def check_inventory(state: OrderState) -> dict:
    item = state["item"]
    quantity = state["quantity"]
    steps = _steps(state)
    if inventory[item] >= quantity:
        inventory[item] -= quantity
        steps.append(f"Inventory available. Deducted {quantity} from {item}.")
        return {"steps": steps}
    return {"steps": steps}


def route_after_inventory(state: OrderState) -> str:
    item = state["item"]
    return "calculate_price" if inventory[item] >= 0 and state.get("steps", [])[-1:] and state["steps"][-1].startswith("Inventory available.") else "conditional_substitution"


def conditional_substitution(state: OrderState) -> dict:
    steps = _steps(state)
    current_item = state["item"]
    current_index = SUBSTITUTION_ORDER.index(current_item)
    rejected_count = state.get("rejections_count", 0)

    if rejected_count >= 2:
        steps.append("Customer rejected both alternative offers. Order canceled.")
        return {
            "status": "rejected",
            "steps": steps,
            "message": "מצטערים שלא מצאנו תחליף מתאים. ביטלנו את ההזמנה, ונשמח לעזור בפעם הבאה.",
        }

    # After the first rejected offer, continue searching after that offered
    # product. The original requested item remains in state until acceptance.
    candidates = SUBSTITUTION_ORDER[current_index + 1 :]
    if rejected_count == 1:
        first_offer = next(
            (name for name in candidates if inventory[name] >= state["quantity"]),
            None,
        )
        if first_offer is not None:
            first_index = SUBSTITUTION_ORDER.index(first_offer)
            candidates = SUBSTITUTION_ORDER[first_index + 1 :]

    next_item = next(
        (name for name in candidates if inventory[name] >= state["quantity"]),
        None,
    )
    if next_item is None:
        steps.append("No substitution item has enough stock")
        return {
            "status": "rejected",
            "steps": steps,
            "message": "מצטערים, אין לנו כרגע מלאי מספיק למאפה שביקשת או לתחליף מתאים. נשמח לנסות שוב ביום אחר.",
        }

    if rejected_count == 0:
        steps.append(
            f"Offered alternative {next_item} (Offer 1). Customer rejected Offer 1."
        )
        return {"rejections_count": 1, "steps": steps}

    if rejected_count == 1:
        inventory[next_item] -= state["quantity"]
        steps.append(
            f"Offered alternative {next_item} (Offer 2). Customer accepted Offer 2."
        )
        return {"item": next_item, "steps": steps}

    steps.append("Customer rejected both alternative offers. Order canceled.")
    return {
        "status": "rejected",
        "steps": steps,
        "message": "מצטערים שלא מצאנו תחליף מתאים. ביטלנו את ההזמנה, ונשמח לעזור בפעם הבאה.",
    }


def route_after_substitution(state: OrderState) -> str:
    if state.get("status") == "rejected":
        return END
    return "calculate_price" if state.get("item") != "babka" and state.get("steps", [])[-1].endswith("accepted Offer 2.") else "conditional_substitution"


def calculate_price(state: OrderState) -> dict:
    subtotal = PRICES[state["item"]] * state["quantity"]
    steps = _steps(state)
    if subtotal > 150 and state["day"] != "Friday":
        subtotal *= 0.85
        steps.append("15% discount applied for orders over 150 ILS")
    elif subtotal > 150 and state["day"] == "Friday":
        steps.append("Order over 150 ILS but no discount applied because it is Friday")

    shipping_cost = 20.0 if state.get("delivery") == "delivery" else 0.0
    total = round(subtotal + shipping_cost, 2)
    fulfillment = "משלוח לכתובתך" if state.get("delivery") == "delivery" else "איסוף עצמי"
    item_name = DISPLAY_NAMES[state["item"]]
    steps.append("Price calculated and order finalized")
    message = (
        f"איזה כיף, ההזמנה שלך מוכנה: {state['quantity']} × {item_name}. "
        f"הסכום לתשלום הוא {total:.2f} ש״ח, כולל {fulfillment}. נתראה בקרוב!"
    )
    return {"total": total, "status": "accepted", "steps": steps, "message": message}


builder = StateGraph(OrderState)
builder.add_node("validate_order", validate_order)
builder.add_node("check_shipping", check_shipping)
builder.add_node("check_inventory", check_inventory)
builder.add_node("conditional_substitution", conditional_substitution)
builder.add_node("calculate_price", calculate_price)

builder.add_edge(START, "validate_order")
builder.add_conditional_edges(
    "validate_order",
    route_after_validation,
    {"check_shipping": "check_shipping", END: END},
)
builder.add_edge("check_shipping", "check_inventory")
builder.add_conditional_edges(
    "check_inventory",
    route_after_inventory,
    {"calculate_price": "calculate_price", "conditional_substitution": "conditional_substitution"},
)
builder.add_conditional_edges(
    "conditional_substitution",
    route_after_substitution,
    {"calculate_price": "calculate_price", "conditional_substitution": "conditional_substitution", END: END},
)
builder.add_edge("calculate_price", END)
graph = builder.compile()


def reset_daily_inventory() -> None:
    """Restore the initial stock, for example at the start of a new day."""
    inventory.clear()
    inventory.update(INITIAL_INVENTORY)


if __name__ == "__main__":
    # Invocation template requested in prompt.md:
    result = graph.invoke({"item": "babka", "quantity": 2, "day": "Thursday", "city": "Jerusalem"})
    print(result["message"])

# In a notebook, render the graph with:
# from IPython.display import Image, display
# display(Image(graph.get_graph().draw_mermaid_png()))
