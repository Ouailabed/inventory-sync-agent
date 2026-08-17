# Inventory Sync Agent

This is my build for the AI Engineering Intern assessment at LEC AI.

## What this does

I built an agent that keeps stock numbers in sync across 3 warehouse systems that do not share a database. Each warehouse has its own way of naming things, its own storage, and no idea the other two exist. The agent reads all three, finds where they disagree, decides what to do, and fixes it. No human clicks anything.

The part I spent most of my time on is idempotency. Running the agent twice on the same problem must not fix it twice, send the same alert twice, or write the same thing twice into its records. The brief said this was the most important part, so that is where I put the effort.

## The 3 warehouses

Each warehouse is a small web service. It runs in its own process, on its own port, and saves its data to its own file. They each use different field names on purpose, so they really behave like separate systems instead of copies of each other:

| Warehouse | Port | Field for the product | Field for the amount |
|---|---|---|---|
| A | 8001 | `sku_id` | `qty` |
| B | 8002 | `product_code` | `quantity` |
| C | 8003 | `item` | `stock_level` |

Warehouse C also allows negative numbers. That is how overselling shows up in real data: the system says you have -3 of something, which is impossible, so something went wrong earlier.

The agent talks to them over HTTP, like it would talk to any real service.

## How it works

1. **Ask** - the agent calls all 3 warehouse services and asks for their stock.
2. **Translate** - each warehouse answers in its own words, so the agent turns all of them into one simple shape: `{sku, qty}`.
3. **Compare** - it looks for 4 kinds of problems:
   - `quantity_mismatch` - the systems disagree about how much stock there is
   - `missing_sku` - a product exists in some systems but not others
   - `negative_stock` - a system says the stock is below zero
   - `data_error` - a warehouse sent something the agent cannot use, or did not answer at all
4. **Decide** - simple rules, nothing clever:
   - If 2 or more systems agree on a number, change the one that disagrees to match them
   - If they cannot agree, ask for a real physical count in the warehouse
   - Unless the only reason they cannot agree is a warehouse we could not read. Then tell a human to fix the data first
   - If a product is missing from a system, tell a human. Creating stock automatically felt too risky to me
   - If stock is negative, ask for a real count. I cannot guess the true number just from seeing it is negative
   - If the data is broken, tell a human. There is nothing safe to calculate from broken data
5. **Do it** - the fix is sent to the warehouse service, and the decision is written to the log.
6. **Remember** - every problem gets a fingerprint. The fingerprint is built from the SKU, the problem type, and the exact numbers involved. Before acting, the agent checks if it already handled this exact situation. If yes, it skips it. This is what makes running it again safe.

## Proof that running it twice is safe

I checked this in three ways.

**By hand.** I ran the agent twice, one after the other. The first run made 4 fixes. The second run made 0 new fixes and skipped 3.

```
=== RUN 1 ===
CORRECTED: set SKU-001 to 50 in warehouse B
FLAGGED: SKU-002 - missing from ['B']
RECOUNT TRIGGERED: SKU-002 - negative stock in C
FLAGGED: SKU-003 - missing from ['A', 'C']
New actions taken: 4

=== RUN 2 ===
SKIPPED (already handled): SKU-002 - missing_sku
SKIPPED (already handled): SKU-002 - negative_stock
SKIPPED (already handled): SKU-003 - missing_sku
New actions taken: 0
```

**With a new problem added.** This one matters more to me. After the two runs above, I changed a number in warehouse C to create a completely new problem. Then I ran the agent a third time. It fixed only the new problem and still skipped the old three:

```
=== RUN 3, after changing warehouse C ===
CORRECTED: set SKU-001 to 50 in warehouse C
SKIPPED (already handled): SKU-002 - missing_sku
SKIPPED (already handled): SKU-002 - negative_stock
SKIPPED (already handled): SKU-003 - missing_sku
New actions taken: 1
```

This proves the agent is really comparing what it sees against what it did before. It is not just refusing to do anything after the first run.

**With tests.** There are 37 tests. They cover reruns, broken data, a warehouse being switched off, ties, the scheduler, the lock, and the log format.

One small thing that looks strange but is not a bug: run 1 sees 4 problems and run 2 sees only 3. That is because the mismatch in run 1 was really fixed, so it is not a problem any more and there is nothing left to find. The other 3 still exist, so they are found again and then skipped. Two different things are happening, and the report shows both.

## Two things I want to flag honestly

**1. One problem was being reported twice.**

When I first ran the detector, SKU-002 showed up two times. Once as `negative_stock`, because warehouse C said -3. And once as `quantity_mismatch`, because warehouse A said 12 and C said -3.

These are not two problems. They are one problem seen from two sides. My first choice was to leave both, because each one is technically true and they are found by separate checks. Then I changed my mind. If a number is negative, of course it will not match the others, so the mismatch adds nothing. And the fix for negative stock is a physical count, which also solves the mismatch.

So now the detector skips the mismatch when the same SKU already has negative stock. The conflict count went from 5 to 4, and 4 is the honest number.

**2. A real bug that taught me something.**

My first version of the warehouses kept stock in a normal Python dictionary, in memory. When the agent "fixed" warehouse B, it worked. Inside that one run. But as soon as I started a new process to check, the old number was back. The dictionary was just rebuilt from zero every time the file was imported. Nothing was ever saved.

This is obvious once you see it, but I think it is worth writing down. It is exactly the kind of bug that breaks a real system quietly. The log would say "corrected" and nothing would have changed. I fixed it by making each warehouse save to its own file on disk. After that the fixes stayed, and that is also what let me prove idempotency properly instead of faking it.

## The 7 things I added on top

The brief said not to stop at the minimum, so I kept going. Here is each one, and why.

**1. I stopped the agent reporting the same problem twice.**

This is the SKU-002 story above. One real problem should be one item on the list, not two.

**2. I made it survive bad data.**

What happens if a warehouse sends something broken? I tried it, and the whole agent crashed. Three different ways: a broken file, a record with a missing field, and a quantity that was text instead of a number.

Now the agent checks every record before it uses it. If one record is bad, it puts that one aside, marks it for a human, and keeps working on everything else. One bad row in one warehouse should not block fixes in the other two.

The most important part is this: **if a warehouse does not answer, the agent does not say the products are missing from it.** It does not know. "Missing" and "I could not read it" are two very different things, and mixing them up would mean the agent invents a pile of fake problems and hides the one real one.

I also chose not to guess. If a quantity says "fifty" instead of 50, I could turn it into a number. But this agent writes numbers into real stock systems. If the value was something like "45 units" my guess would be wrong, and a wrong number in a stock system is worse than an open question. So it asks a human.

**3. I made it smarter when nobody agrees.**

What if all three warehouses say something different? Before, the agent just put it on a list for a human to look at. But that human knows nothing more than the agent does. They will open the ticket, see three different numbers, and order a physical count. So now the agent asks for the count directly.

There is one exception I am happy about. Before ordering a count, the agent asks *why* it could not decide. If the reason is that one warehouse was unreadable, then this is a software problem, not a stock problem. Sending a person to walk around the warehouse and count boxes is too expensive for a broken file. So in that case it says: fix the data first, then run again.

While writing this I also found a real bug in the old code. The old rule was "if 2 or more systems agree, they win." With 3 warehouses that is fine. But with 4 warehouses you can get 2 against 2, and the old code would pick one side almost at random and overwrite the other two. It cannot happen today with 3 warehouses, but it would happen the day someone adds a fourth. I fixed it and wrote a test for it.

**4. I added a lock, so two copies cannot work at the same time.**

Running the agent twice one after the other was already safe. But running two copies at the *same moment* was not. Both read the records before either one wrote anything, both thought "nobody handled this yet," and both did the work.

I did not want to just claim this, so I proved it. I started two agents at the same second and both applied the same fix and sent the same alert twice.

The fix is like a sign on a door that says "someone is already working in here." Before starting, the agent puts up the sign. If the sign is already there, it stops and says so. When it finishes, it takes the sign down.

One detail I am proud of. The obvious way to write this is: check if the sign is there, and if not, put it up. But that has the exact same bug it is trying to fix. Two agents can both look, both see nothing, and both put up a sign. So instead I let the operating system do it. It creates the file only if the file is not already there, in one single step that cannot be split. Only one agent can win that, whatever the timing is.

The sign is also taken down if the agent crashes.

**5. I turned the warehouses into real services.**

Before, the three warehouses were just Python files that the agent imported. That is not really "three disconnected systems," it is one program pretending.

Now each warehouse is a small FastAPI service. Own process, own port, own storage. The agent sends real HTTP requests to them. If you stop one with Ctrl-C, the agent really cannot reach it.

The nice surprise was that this needed almost no new error handling. The work from point 2 already covered it. A service that is switched off arrives at the same place in the code as a file that cannot be read. So a dead warehouse is handled the same way: flag it, do not guess what it has, keep working with the other two.

Going over the network did create one new problem, and I handled it. A warehouse can be alive when the agent reads from it and dead when the agent writes to it. The old code wrote every action into its records straight away. That means a fix that failed would be marked as done and never tried again. The records would be lying. Now a fix is only written down if it actually worked. Failed ones are counted separately and tried again on the next run.

**6. I made it run by itself.**

The agent can now run on a timer with `--interval 30` instead of waiting for me to start it.

This is where idempotency stops being a nice idea and becomes the whole point. Nobody is watching these runs. If the agent was not safe to rerun, it would keep re-fixing the same thing every 30 seconds, forever, and nobody would notice.

I tested it live. Run 1 fixed the problem and run 2 did nothing. Then I changed a warehouse while the timer was still going, and run 3 picked up only that new problem.

A run that fails does not kill the timer. It writes down what went wrong and tries again on the next round. An agent that dies quietly on its first bad day is worse than no agent.

**7. I made the log readable by machines.**

The log used to be normal sentences. Nice for a person, useless for a computer. If I wanted to ask "how many fixes failed this week," I would have to search through text.

Now every line is one JSON object with the time, what happened, which SKU, which action, and the details. I kept the human sentence inside each line too, so the file is still easy to read.

While doing this I found the old log was worse than I thought. The summary at the end of each run was written as one entry, but it was 12 lines long. So the file was not even one-entry-per-line as plain text. Anything reading it line by line was already getting nonsense.

## How to run it

I am on Windows, so I use `python`. On Mac or Linux use `python3`.

**First, install what it needs:**

```bash
python -m pip install -r requirements.txt
```

**Then start the 3 warehouses. Keep this terminal open:**

```bash
python start_warehouses.py
```

**In a second terminal, run the agent:**

```bash
python executor.py
```

Other things you can do:

```bash
# show what it would do, change nothing
python executor.py --dry-run

# run again every 30 seconds, Ctrl-C to stop
python executor.py --interval 30

# see all options
python executor.py --help

# run all 37 tests
python -m pytest
```

The tests start their own warehouse services, so you do not need to start them first for that.

To see the agent handle a warehouse being down, stop one of the services and run the agent again.

## The files

**The agent**

| File | What it is for |
|---|---|
| `executor.py` | The main entry point. Runs one sync, or runs on a timer. |
| `detect_conflicts.py` | Asks all 3 warehouses for their stock and finds the problems. |
| `decide.py` | The rules for what to do about each problem. |
| `normalize.py` | Turns each warehouse's field names into one shape, and checks the data is usable. |
| `ledger.py` | The record of problems already handled. This is what makes reruns safe. |
| `lock.py` | The "someone is already working here" sign. |
| `agent_log.py` | Writes the log, one JSON object per line. |
| `warehouse_client.py` | Talks to the 3 services over HTTP. |

**The warehouses**

| File | What it is for |
|---|---|
| `warehouses/warehouse_a.py` | Warehouse A service, port 8001. |
| `warehouses/warehouse_b.py` | Warehouse B service, port 8002. |
| `warehouses/warehouse_c.py` | Warehouse C service, port 8003. |
| `start_warehouses.py` | Starts all 3 at once. |

**The tests (37 total)**

| File | What it checks |
|---|---|
| `test_idempotency.py` | The second run does not repeat the first run's work. |
| `test_concurrency.py` | Two agents at the same moment: one works, one stops. |
| `test_data_errors.py` | Broken data does not crash the run or invent fake problems. |
| `test_service_down.py` | A warehouse that is switched off is not treated as empty. |
| `test_tie_breaker.py` | The right choice is made when systems agree, disagree, or tie. |
| `test_scheduler.py` | Timed runs act once, survive a bad run, and clean up properly. |
| `test_logging.py` | Every log line is valid JSON. |
| `conftest.py` | Starts the real warehouse services for the tests. |

**Made while running, not part of the code:** `ledger.json`, `sync_log.txt`, `agent.lock`, and the three `warehouse_*_data.json` files. These are in `.gitignore`, so a fresh copy of the project starts empty.

## What I would do next with more time

- **Send real alerts.** Right now `flag_for_review` and `trigger_recount` only write to the log. In a real system they would send an email or a Slack message, or create a work order.
- **Close the loop on recounts.** The agent can ask for a count, but nothing tells it the count is finished. If someone counts and writes the real number in, the agent notices because the numbers changed. But there is no proper "this is done" step.
- **Say how urgent a recount is.** Negative stock means something is already going wrong, and you are probably selling things you do not have. A three-way tie only means we do not know yet. Both ask for a count, but they are not equally urgent.
- **Make the lock work across machines.** My lock is a file, so it only stops two agents on the same computer. Two agents on two servers would both run. That needs a shared lock, for example in Redis or a database.
- **Deal with a lock left behind after a crash.** If the agent is killed in a hard way, the sign stays on the door and you have to delete `agent.lock` yourself. I decided not to remove old locks automatically. A slow but healthy run could have its lock taken away, and then I would be back to the same bug the lock is there to stop.
- **Think about scale.** Right now every run reads everything from every warehouse. With 3 warehouses that is fast. With 50 warehouses and thousands of products it would not be. I would want each warehouse to tell the agent what changed, instead of the agent asking about everything every time.
- **Use a real database.** JSON files are fine for a demo and easy to read, but they are not safe with many writers.
- **Add authentication.** The warehouse services are open. Anyone who can reach the port can change stock.
- **Small tidying.** Pin the exact versions in `requirements.txt`, and rename `sync_log.txt` to `sync_log.jsonl` since it holds JSON now.
