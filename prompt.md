# Technical Specification for Dana's Bakery LangGraph System

Write a complete, deterministic Python script using LangGraph to process bakery orders. Do not use any live LLM calls or external APIs for routing or calculation. All logic must be hardcoded in Python functions.

## Global Initial State / Inventory
The system starts with the following daily inventory limits:
- Challah: 10
- Sourdough: 4
- Rugelach: 3
- Babka: 0

Prices (ILS):
- Challah: 18
- Babka: 45
- Rugelach: 30
- Sourdough: 25

Substitution Order Hierarchy:
Babka -> Rugelach -> Sourdough -> Challah

## State Schema
The graph state typed dictionary must contain the following keys exactly:
- item (str): The product sold (original or substituted)
- quantity (int): The amount ordered
- day (str): Day of the week
- city (str): Customer's city
- status (str): "accepted" or "rejected"
- delivery (str): "pickup" or "delivery"
- total (float): The final amount to pay, including shipping and discounts
- message (str): The warm, human-like response to the customer in Hebrew
- steps (list of str): Chronological log of steps the order went through, in order
- rejections_count (int): Counter tracking the number of alternative offers rejected by the customer (default=0)

## Graph Nodes & Deterministic Logic

1. validate_order:
- If quantity < 1, or any field (item, day) is empty/None: set status="rejected", add step "Validation failed: missing fields or invalid quantity", generate a polite explanation message in Hebrew stating that the order could not be understood, and route immediately to END.
- Otherwise, add step "Order validated successfully" and route to check_shipping.

2. check_shipping:
- If city is empty, None, or empty string: set delivery="pickup", shipping_cost=0, add step "No city provided, set to pickup (free)".
- If city == "Jerusalem": set delivery="delivery", shipping_cost=20, add step "Delivery to Jerusalem set (20 ILS)".
- If city is anything else: set delivery="pickup", shipping_cost=0, add step "City outside Jerusalem, automatically changed to pickup (free) and customer notified".
- Route to check_inventory.

3. check_inventory:
- Check if current daily inventory for the requested `item` is greater than or equal to `quantity`.
- If YES: deduct `quantity` from that item's inventory, add step f"Inventory available. Deducted {quantity} from {item}.", route to calculate_price.
- If NO: route to conditional_substitution.

4. conditional_substitution:
- Evaluate the substitution chain based on the current item. Look for the next item down the chain (Babka -> Rugelach -> Sourdough -> Challah) that has an available inventory >= `quantity`.
- If NO alternative item has enough inventory, set status="rejected", add step "No substitution item has enough stock", generate an apology message in Hebrew, and route to END.
- Simulate customer decisions based on `rejections_count`:
  - If rejections_count == 0: Increment rejections_count by 1. Add step f"Offered alternative {next_available_item} (Offer 1). Customer rejected Offer 1." Re-evaluate conditional_substitution to find the next item down the chain.
  - If rejections_count == 1: The customer ACCEPTED this second offer. Update `item` to this new product name. Deduct `quantity` from this item's inventory. Add step f"Offered alternative {next_available_item} (Offer 2). Customer accepted Offer 2." Route to calculate_price. (DO NOT CANCEL THE ORDER).
  - If rejections_count >= 2: The customer has rejected both Offer 1 and Offer 2. Set status="rejected", add step "Customer rejected both alternative offers. Order canceled.", generate a polite apology message in Hebrew, and route to END.

5. calculate_price:
- subtotal = price_of_item * quantity
- If subtotal > 150 and day != "Friday": apply a 15% discount on the baked goods (subtotal = subtotal * 0.85). Add step "15% discount applied for orders over 150 ILS".
- If day == "Friday" and subtotal > 150: Do not apply discount. Add step "Order over 150 ILS but no discount applied because it is Friday".
- total = subtotal + shipping_cost
- set status="accepted"
- Add step "Price calculated and order finalized".
- Generate a warm, personal, human-like message in Hebrew (`message`) summarizing the final sold item, quantity, total price, and fulfillment method (pickup/delivery).
- Route to END.

## Output Requirements
- Define the state using TypedDict.
- Compile the graph.
- Provide the code snippet using `draw_mermaid_png()` to display the graph visually in a notebook.
- Include a structural invocation template exactly like this:
  `result = graph.invoke({"item": "babka", "quantity": 2, "day": "Thursday", "city": "Jerusalem"})`
