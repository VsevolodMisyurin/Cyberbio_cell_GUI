# Simulator Bio-Mechanics: σ-Scale Parameter Reference

## What is a sigma (σ)?

All concentrations in the simulator — food, energy, toxins, cellular products — are expressed in **σ units** (standard deviations). The scale is symmetric around zero:

| Value | Meaning |
|-------|---------|
| −3 σ | Critically low / essentially absent |
|  0 σ | Average, baseline level |
| +3 σ | Very high / critically abundant |

±3 σ are hard environmental limits for most variables. Inside the cell, energy can drop below −3 σ, which leads to cell death.

---

## 1. Food

### How food works in the environment

Food is stored in σ units and **regenerates by +1 σ every tick** — a baseline nutrient influx. The value is clamped to [−3, +3] σ.

The starting food level is set in the environment editor (default −3 σ — nearly empty).

### How genes extract energy from food

Genes with the `energy` function (e.g. HARVEST, FEED, SAFEED) convert food into cellular energy.

**Per-tick formula:**

```
available = food − (−3.0)                      # food above the floor
used      = min(available, eff_prot × coeff)   # how much the gene can process
energy   += used × efficiency                   # credited to the cell
food     −= used × support_ratio               # deducted from the shared environment
```

**Efficiency** depends on the food level at the start of the tick (`init_food`, before regeneration):

| Food level (init_food) | Processing efficiency |
|------------------------|----------------------|
| −3 σ (scarce)  | 0.50  (50 %) |
| −2 σ           | 0.67  (67 %) |
| −1 σ           | 0.83  (83 %) |
|  0 σ           | 1.00  (100 %) |
| +1 σ           | 1.33  (133 %) |
| +2 σ           | 1.67  (167 %) |
| +3 σ (plentiful) | 2.00 (200 %) |

Exact formula:
- If `init_food ≤ 0`: `eff = 0.5 + (init_food + 3) × (0.5 / 3)`
- If `init_food > 0`: `eff = 1.0 + init_food × (1.0 / 3)`

**In practice:** at a near-empty environment (−3 σ) a cell extracts half as much energy from the same mass of processed food. At abundance (+3 σ) it extracts twice as much as at baseline.

**support_ratio** — the fraction of the environment's capacity occupied by the population:

```
support_ratio = total_cell_count / support_cell_num
```

A large population depletes the shared food pool faster — resource competition.

---

## 2. Cellular Energy

Energy is the cell's internal balance in σ units. Unlike food, energy is **not clamped**: it can go deeply negative, which leads to death.

### Sources of energy gain
- Food processing by `energy` genes (see Section 1)
- Protein recycling by `process` genes (autophagy)
- mRNA digestion by `RNAdigest` genes

### Sources of energy loss
- **Expression maintenance:** every tick `sum(new_expr) × energy_cost` is deducted
  - `energy_cost = 1 / (gene_count × 16)` — scales with genome size
- **Division:** `division_cost` is deducted (set by the `div` gene's coefficient)
- **Toxins:** direct energy penalties (see Section 3)
- **Secretion:** `secret` genes deduct `delta × energy_cost_per_unit`

### Cell death probability

The probability of a single cell dying in one tick follows a **logistic function** of the absolute energy value:

```
death_prob = 1 / (1 + exp(−3 × (|energy| − 3.5)))
```

| Energy | Death probability per tick |
|--------|---------------------------|
|  0 σ  | ≈ 0.02 % (negligible) |
| ±1 σ  | ≈ 0.06 % |
| ±2 σ  | ≈ 0.4 % |
| ±3 σ  | ≈ 7 % |
| ±4 σ  | ≈ 62 % |
| ±5 σ  | ≈ 95 % |

The function is **symmetric** — cells die from both starvation (energy → −∞) and, theoretically, extreme surplus (energy → +∞), though the latter is rare in practice.

At population ≤ 100 death is stochastic (each cell rolls independently). Above 100 cells a deterministic approximation is used: `survived = int(N × (1 − death_prob))`.

---

## 3. Toxins

### Toxin concentration in σ units

Each toxin's starting level is set in the environment editor. For example, −2 σ means the toxin is present at a low background level; +1 σ is a noticeable concentration.

The level changes over time:
- **Increases** from cellular products (Wastetoxin, CytokineX, etc.)
- **Decreases** from `detox` genes

### How toxins deal damage: `toxin_effect`

```
effect = base_effect × exp(sigma)
```

The exponential response means **each +1 σ multiplies the effect by e ≈ 2.718**.

| Toxin sigma | Effect (base_effect = 0.2) |
|-------------|---------------------------|
| −3 σ | 0.2 × e⁻³ ≈ 0.010 |
| −2 σ | 0.2 × e⁻² ≈ 0.027 |
| −1 σ | 0.2 × e⁻¹ ≈ 0.074 |
|  0 σ | 0.2 × e⁰  = 0.200 |
| +1 σ | 0.2 × e¹  ≈ 0.544 |
| +2 σ | 0.2 × e²  ≈ 1.478 |
| +3 σ | 0.2 × e³  ≈ 4.018 (hard upper limit) |

Sigma is clamped to [−8, +3] when computing the effect.

### Target parameter (`param`)

| param | What is penalised |
|-------|------------------|
| `energy` | Direct energy deduction: `energy −= effect` |
| `TPM`    | Expression growth penalty: `new_expr ×= (1 − min(effect, 1))` |
| `common` | Both energy AND TPM simultaneously |

### Detoxification: `detox` gene

A `detox` gene reduces the sigma of **all** toxins in the shared environment:

```
detox_power = eff_prot × cell_count × coeff × support_ratio
new_sigma   = max(−3.0, sigma − detox_power)
```

Because detox acts on the **shared environment**, every genome benefits — including competitors.

### Toxin resistance: `toxresist` gene

Unlike `detox`, a `toxresist` gene does **not clean the environment**. It reduces `local_penalties` only for the cell that expresses it:

```
reduction      = prev_prot × coeff
local_penalty  = max(0, tox_penalty − reduction)
```

The toxin sigma in the environment remains unchanged — other genomes receive no benefit.

### Toxin detection: `toxsens` gene

Detection is probabilistic. The gene computes a detection score:

```
score = (expr × exp(total_toxins)) / (64 × detect_coeff)
```

If `score > 1` the toxin is considered detected (`Toxin_detected = True`), making the condition `Toxin_detected == True` available to other genes. At low toxin concentration or low gene expression the sensor may remain silent.

---

## 4. Cellular Products

Products accumulate in the environment starting from −3 σ. Each tick the following is added to the product level:

```
total_delta  = delta_per_cell × support_ratio
env_product += total_delta
```

### Secretion modes

| Source (`mode`) | Formula for `delta_per_cell` |
|-----------------|------------------------------|
| `energy`        | `coeff × energy_spent_this_tick` |
| `TPMsum`        | `coeff × sum(all TPM of the cell)` |
| `secret:<gene>` | `coeff × protein_level[gene]` |

**support_ratio** ensures that a larger population secretes proportionally more product.

### Wastetoxin (mandatory)

Wastetoxin is always secreted in proportion to energy spent (`mode = energy`, `coeff = 0.005`). It is unavoidable — metabolic waste is produced by any cellular activity. If Wastetoxin is registered as a toxin in the environment, its accumulation poisons the medium at high population density.

### CytokineX (optional)

CytokineX is secreted in proportion to total transcriptional activity (`mode = TPMsum`, `coeff = 0.0001`). High total expression of all genes → high CytokineX secretion.

### Protein-driven secretion (`secret` gene function)

When a gene has the `secret` function, its protein directly secretes a product into the environment. The secretion rate is proportional to **protein level** (not mRNA), so:
- The effect appears 1–3 ticks after gene activation (protein synthesis lag)
- After the gene deactivates, secretion continues until the protein degrades

The cell pays an energy cost per unit secreted: `energy −= delta × energy_cost_per_unit`. The energy cost does not mutate.

---

## 5. Gene Expression (TPM)

### What TPM means here

TPM (Transcripts Per Million — adapted) is a quantitative measure of a gene's transcriptional activity. Minimum = 1 (gene is silent but not dead). Maximum is set by the enhancer.

### Expression growth

Every tick while the gene is active:

```
new_expr = min(prev_expr × promoter, enhancer)
```

- **Promoter** (numeric multiplier): typical starting values 1.25 / 2.0 / 4.0. At promoter = 2.0 expression doubles every tick.
- **Enhancer** (numeric ceiling): typical starting values 4 / 16 / 64. Sets the maximum expression level.

Example: a gene with promoter 2.0 and enhancer 16 reaches its cap in 4 ticks: 1 → 2 → 4 → 8 → 16.

Both the promoter multiplier and the enhancer cap can drift continuously through mutation (±10 % per mutation event, no hard clamp beyond keeping values positive).

TPM-type toxins reduce expression growth: `new_expr ×= (1 − tpm_penalty)`.

### Gene activation

A gene transitions to `active` status when:
1. All ON conditions evaluate to True
2. No OFF condition evaluates to True
3. `new_expr ≥ threshold` (TPM has reached the activation threshold)

**Hysteresis:** when an OFF condition is met, deactivation is delayed by one tick, preventing instantaneous oscillations.

### Protein

Protein is synthesised from the previous tick's mRNA and undergoes decay:

```
protein = prev_protein × stability × size_modifier(kDa) + max(0, prev_expr − 1)
```

- `stability` is a global parameter (0–1)
- `size_modifier`: proteins ≤ 10 kDa are most stable (multiplier 1.0); proteins ≥ 150 kDa degrade 4× faster (multiplier 0.25); linear interpolation between the extremes

A gene's function (`energy`, `detox`, `div`, etc.) is executed only when `protein ≥ threshold`.
