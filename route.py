# SHIELD v1 - Stage 5: Query Understanding & Routing
#
# Refactored additions vs previous version:
#
#  New fields in QueryPayload:
#   purpose            - WHY data is processed. Changes legal basis entirely.
#                        "model training" vs "direct patient care" → different
#                        GDPR Art.9(2) exception, different MDR applicability.
#   deployment_context - WHERE the system operates. Triggers:
#                        "workplace"    → EU AI Act Art.5 prohibition on emotion AI
#                        "hospital"     → MDR conformity assessment required
#                        "public space" → real-time biometric ID prohibited
#
#  Improved intent classification:
#   - "who is responsible / liable" questions → knowledge (not scenario)
#   - "do I need approval / certification"     → scenario (regulatory approval)
#   - "what are our obligations"               → scenario (derive from activity)
#   - Stakeholder framing (founder/engineer/investor) → same intents, no new branch
#     (framing affects phrasing, not the regulatory analysis)
#
#  Why purpose matters (examples from real user questions):
#   training a model on medical records → purpose="AI model training"
#     → GDPR Art.9(2)(j) research exemption, NOT Art.9(2)(h) direct care
#   emotion detection in workplace      → purpose="workplace productivity"
#     → EU AI Act Art.5 prohibition fires (workplace context is the trigger)
#   patient vitals AI in hospital       → purpose="clinical decision support"
#     → MDR conformity required + high-risk AI obligations
#
#  Why deployment_context matters:
#   Same system in different contexts → completely different regulatory obligations
#   Emotion recognition: workplace → PROHIBITED | research lab → regulated but not banned
#   Biometric AI:        hospital  → MDR + high-risk AI | transport → GDPR + EU AI Act only

import os
import re
import sys
import json
import time
from typing import Optional, Literal
from dotenv import load_dotenv
from pydantic import BaseModel, field_validator, ValidationError

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
MODEL        = "meta-llama/llama-4-scout-17b-16e-instruct"
MAX_RETRIES  = 2
RETRY_DELAY  = 2

QUESTION = ("Can my elderly-care assistant store fall-risk predictions "
            "and share them with caregivers?")


class QueryPayload(BaseModel):
    intent: Literal[
        "scenario",               # specific activity to assess compliance for
        "knowledge",              # explain/define a rule, concept, or obligation
        "greeting",               # hi, hello, hey
        "help",                   # what can you do?
        "examples",               # give me example questions
        "clarify",                # ambiguous - could be personal OR compliance question
        "sensitive",              # harm, violence, self-harm - safety gate
        "medical_advice",         # personal clinical/medication question, no compliance angle
        "unsupported_regulation", # law outside GDPR/AI Act/MDR scope
        "out_of_scope",           # nothing to do with compliance, AI, health, devices
    ]

    # Scenario fields (scenario intent only)
    data_type:  Optional[str] = None  
                                               
    action:             Optional[str] = None   
    system_type:        Optional[str] = None   
    recipients:         Optional[str] = None   
    purpose:            Optional[str] = None   
    deployment_context: Optional[str] = None

    #  Knowledge field (knowledge intent only) 
    topic:              Optional[str] = None   
    # Shared optional 
    jurisdiction:       Optional[str] = None  

    @field_validator("data_type", "action", "system_type", "recipients",
                     "purpose", "deployment_context", "topic", "jurisdiction")
    @classmethod
    def tidy(cls, v):
        if v is None:
            return None
        v = " ".join(v.split())
        return v or None


_SOCIAL_RE = re.compile(
    r"^\s*("
    r"hi+|hello+|hey+|hiya|howdy|yo+|sup|greetings|"
    r"good\s*(morning|afternoon|evening|day)|"
    r"what'?s\s*up|"
    r"how'?s\s+(it\s+going|life|things|everything|you\s+doing)|"
    r"how\s+are\s+you"
    r")\W*$",
    re.IGNORECASE,
)
_HELP_RE = re.compile(
    r"^\s*(what\s+can\s+you\s+do|how\s+do\s+you\s+work|what\s+do\s+you\s+do"
    r"|help|how\s+can\s+you\s+help|what\s+are\s+you|who\s+are\s+you"
    r"|what\s+is\s+shield|tell\s+me\s+about\s+yourself)\W*$",
    re.IGNORECASE,
)
_EXAMPLES_RE = re.compile(
    r"^\s*(give\s+me\s+(some\s+)?(example|sample)\s*(questions?)?|"
    r"(show|list)\s+(me\s+)?(example|sample)\s*(questions?)?|"
    r"what\s+(kind\s+of\s+)?(questions?\s+can\s+I\s+ask|can\s+I\s+ask)"
    r"|example questions?)\W*$",
    re.IGNORECASE,
)

def _deterministic_intent(question: str) -> Optional[str]:
    q = question.strip()
    if _SOCIAL_RE.match(q):   return "greeting"
    if _HELP_RE.match(q):     return "help"
    if _EXAMPLES_RE.match(q): return "examples"
    return None
  
  


# Routing system prompt
SYSTEM = """You are the routing layer of SHIELD, a healthcare AI and medical device
compliance assistant covering GDPR, the EU AI Act, EU MDR 2017/745, UK MDR 2002,
and the Data (Use and Access) Act 2025 (DUAA 2025).

Your job is to classify the user's intent and extract structured fields so the
downstream pipeline can retrieve the right regulatory context.

Users include founders, engineers, researchers, and investors - all asking about
compliance obligations for real products. Extract what they are actually asking about
regardless of how they phrase it.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
JURISDICTION INFERENCE (check first)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
If a country/region is mentioned, populate "jurisdiction":
  UK / England / Scotland / Wales / Northern Ireland → "UK"
    (UK jurisdiction: UK MDR 2002 and DUAA 2025 apply alongside UK GDPR)
  Any EU member state → "EU"
  Both UK and EU mentioned → "EU+UK"
  Outside EU/UK (USA, India, etc.) → "other:<country>"
  Not mentioned → null

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INTENT CLASSIFICATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"scenario"
  The user describes a specific activity and wants to know if it is compliant,
  permitted, required, or what obligations apply. This includes:
  - "Can I / do I need to / is it allowed to / do we need regulatory approval for..."
  - "What are our obligations for [activity]?" - fill scenario fields, not topic
  - "Is [system/activity] legal under EU law?"
  Fill: data_type, action, system_type, recipients, purpose, deployment_context.

"knowledge"
  The user asks to EXPLAIN, DEFINE, or UNDERSTAND a regulatory rule or concept.
  This includes:
  - "What is / what does X mean / what criteria determine X?"
  - "What technical documentation does X need?" (explaining a requirement)
  - "Who is responsible for GDPR compliance - us or the API provider?"
    → knowledge, topic="controller vs processor liability under GDPR"
  - "Does patient consent cover AI training?" (without a specific system described)
  Fill: topic. Optionally system_type if a specific system is mentioned.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FIELD EXTRACTION RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

data_type  - Normalise to canonical terms:
  "patient vitals", "health records", "medical records", "fall-risk predictions"
    → "Health Data"
  "CVs", "job applications", "employee data"
    → "Personal Data"
  "facial expressions", "fingerprints", "iris scans", "biometric identifiers"
    → "Biometric Data"
  "emotion states", "emotional signals inferred from face/voice"
    → "Emotion Data"
  "location", "GPS", "movement data"
    → "Location Data"
  null if not mentioned.

action  - Describe what is being DONE:
  "store", "share", "process", "train AI model", "deploy", "make automated decisions",
  "detect", "analyse", "score automatically", "recommend", "monitor"
  Use the most specific verb the user mentions. null if not mentioned.

system_type  - The AI system or device described:
  "diagnostic AI", "hiring tool / CV scoring AI", "emotion recognition system",
  "care assistant AI", "LLM / language model", "social care recommendation AI",
  "fatigue detection AI", "medical device software", "wearable device"
  null if not mentioned.

purpose  - WHY the data or system is used. CRITICAL: this changes the lawful basis.
  Examples:
  "clinical decision support" - AI diagnosing or flagging risk for clinicians
  "patient monitoring"        - tracking health status over time
  "direct patient care"       - treatment, therapy, care delivery
  "AI model training"         - using data to train or fine-tune a model
  "research / statistical"    - academic or epidemiological research
  "workplace monitoring"      - monitoring employees, productivity, behaviour
  "hiring / CV screening"     - recruitment and employment decisions
  "loan / credit assessment"  - financial eligibility decisions
  "fraud detection"           - financial security systems
  "safety monitoring"         - driver, industrial, or public safety systems
  "social care intervention"  - recommending care plans for vulnerable people
  "automated significant decision" - decision with legal or similarly significant
                                    effect on individual (triggers DUAA s.80 / Art22)
  null if genuinely not determinable from the question.

deployment_context  - WHERE or IN WHAT SECTOR the system is deployed. CRITICAL:
  same system in different contexts has different obligations.
  "hospital"              - healthcare setting; MDR conformity likely required
  "workplace"             - employment context; EU AI Act Art.5 emotion AI prohibition
  "public space"          - Art.5 real-time biometric ID prohibition may apply
  "vehicle / transport"   - safety systems; not medical device
  "home / home care"      - consumer or care-at-home context
  "financial services"    - credit/loan/insurance; GDPR Art.22 automated decisions
  "education"             - Annex III high-risk AI category
  "social services"       - essential public services; Annex III high-risk AI
  null if not mentioned or not determinable.

recipients  - Who RECEIVES the data or the system's output (not the deployer):
  "caregivers", "hospitals", "third-party API provider", "insurance companies",
  "employers", "loan officers", "patients"
  null if not mentioned.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REMAINING INTENTS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

"clarify"  - The question is ambiguous between personal advice and compliance.
  e.g. "Can I give Panadol to my grandfather?" - personal OR compliance?
  Use ONLY when genuinely unclear. If there is a product/system involved,
  classify as scenario even if phrased colloquially.
  Leave all fields null except jurisdiction.

"sensitive"  - Mentions harm, killing, self-harm, suicide, murder, euthanasia,
  threats. Do NOT classify as clarify or out_of_scope. Leave all fields null.

"medical_advice"  - Personal clinical/medication/emergency question with no
  compliance angle at all. Use "clarify" instead if there IS a compliance angle.

"unsupported_regulation"  - Legal question outside GDPR/AI Act/MDR/DUAA scope:
  employment law, tax law, criminal law, housing law, pharmacy licensing.
  NOTE: DUAA 2025 IS in scope — questions about automated significant decisions,
  opt-out rights, or data intermediaries under UK law → classify as scenario/knowledge.
  Fill topic if identifiable.

"out_of_scope"  - Nothing to do with data protection, AI systems, medical devices,
  or healthcare compliance. Food, sport, entertainment, personal opinions.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Return STRICT JSON only - no prose, no markdown:
{
  "intent": "...",
  "data_type": null or "...",
  "action": null or "...",
  "system_type": null or "...",
  "recipients": null or "...",
  "purpose": null or "...",
  "deployment_context": null or "...",
  "topic": null or "...",
  "jurisdiction": null or "..."
}"""


def call_llm(question: str, nudge: str = "") -> str:
    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY)
    resp = client.chat.completions.create(
        model=MODEL, temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": SYSTEM + nudge},
                  {"role": "user",   "content": question}],
    )
    return resp.choices[0].message.content


# understand_query
def understand_query(question: str) -> Optional[QueryPayload]:
    # Fast path - catches hi/hello/hey/how's life?/what's up/etc.
    fast = _deterministic_intent(question)
    if fast:
        return QueryPayload(intent=fast)

    nudge, last_err = "", ""
    for _ in range(1 + MAX_RETRIES):
        try:
            return QueryPayload.model_validate_json(call_llm(question, nudge))
        except (ValidationError, json.JSONDecodeError, KeyError) as err:
            last_err = f"{type(err).__name__}: {str(err)[:160]}"
            nudge = ("\n\nYour previous reply was rejected: " + last_err +
                     ". Return ONLY valid JSON matching the schema exactly.")
            time.sleep(RETRY_DELAY)
    print(f"[route fail] {last_err}")
    return None


def main():
    question = sys.argv[1] if len(sys.argv) > 1 else QUESTION
    print(f'Question:\n  "{question}"\n')
    payload = understand_query(question)
    if payload:
        print("Structured payload:")
        print(json.dumps(payload.model_dump(), indent=2))


if __name__ == "__main__":
    main()