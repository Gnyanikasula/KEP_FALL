import os
import sys
import json
import time
import types
from pathlib import Path

from owlready2 import get_ontology, default_world, Thing, sync_reasoner_hermit, IRIS, ObjectProperty
import rdflib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DPV_BASE = os.environ.get("DPV_BASE", r"D:\dpv-2.2.1")

OUT_DIR        = os.path.join(BASE_DIR, "OUT_CANDIDATES")
ALIGNMENT_JSON = os.path.join(OUT_DIR, "alignment_results.json")
CLASSES_JSON   = os.path.join(OUT_DIR, "classes_created.json")
OUT_RDF        = os.path.join(OUT_DIR, "dpv-fallrisk-ext-v2.rdf")
OUT_CLASSES_V2 = os.path.join(OUT_DIR, "classes_created_v2.json")
OUT_LOG        = os.path.join(OUT_DIR, "cleanup_log.md")

FALLRISK_NS = "https://w3id.org/kep/fallrisk#"

DPV_MODULES = [
    os.path.join(DPV_BASE, "dpv", "dpv-owl.rdf"),
    os.path.join(DPV_BASE, "pd", "pd-owl.rdf"),
    os.path.join(DPV_BASE, "risk", "risk-owl.rdf"),
    os.path.join(DPV_BASE, "ai", "ai-owl.rdf"),
    os.path.join(DPV_BASE, "legal", "eu", "gdpr", "eu-gdpr-owl.rdf"),
    os.path.join(DPV_BASE, "legal", "eu", "aiact", "eu-aiact-owl.rdf"),
]

# audit decisions for all 146 Thing-fallback classes from the current run
# each DPV target was verified against the live DPV v2.2.1 ontology before use
# DUPLICATE: class duplicates an existing DPV term — remove and redirect references to it
# PARENT:    a real DPV parent was found - reparent under it
# KEEP_THING: no good DPV anchor exists - confirmed correct to remain top-level
AUDIT_DECISIONS = {

    # GDPR Art.9 Para 3 - secrecy exceptions
    "UnionLawSecrecy":               ("PARENT",    "Obligation"),
    "MemberStateLawSecrecy":         ("PARENT",    "Obligation"),

    # GDPR Art.13 - transparency obligations
    "AdequacyDecision":              ("DUPLICATE", "AdequacyDecision"),
    "ThirdCountryTransfer":          ("PARENT",    "Transfer"),
    "AdditionalInformationForFurtherProcessing": ("PARENT", "Notification"),

    # GDPR Art.14
    "ReasonablePeriod":              ("PARENT",    "StorageDuration"),
    "FirstDisclosure":               ("PARENT",    "Notification"),
    "DisproportionateEffort":        ("PARENT",    "Justification"),

    # GDPR Art.17
    "OfferOfInformationSocietyService": ("KEEP_THING", "Art.17 specific condition, no DPV anchor"),
    "PubliclyAvailablePersonalDataErasure": ("PARENT", "Obligation"),

    # GDPR Art.18
    "RestrictionForLegalClaims":     ("KEEP_THING", "Art.18 specific concept, no DPV anchor"),

    # GDPR Art.32
    "ApprovedCodeOfConduct":         ("PARENT",    "CodeOfConduct"),

    # GDPR Art.35
    "ListOfProcessingActivities":    ("PARENT",    "RecordsOfActivities"),
    "MonitoringOfBehaviour":         ("PARENT",    "BehaviourAnalysis"),

    # EU AI Act Art.5 - prohibited practices
    "SubliminalTechnique":           ("KEEP_THING", "specific prohibited AI technique, no DPV anchor"),
    "WorkplaceEmotionInference":     ("KEEP_THING", "specific prohibited practice, no DPV anchor"),
    "MedicalEmotionInference":       ("KEEP_THING", "specific prohibited practice, no DPV anchor"),

    # EU AI Act Art.6 - classification
    "UnionHarmonisationLegislation": ("KEEP_THING", "legislative instrument concept, no DPV anchor"),
    "DelegatedActs":                 ("KEEP_THING", "regulatory instrument concept, no DPV anchor"),
    "DelegatedAct":                  ("KEEP_THING", "regulatory instrument concept, no DPV anchor"),
    "ConcreteEvidence":              ("KEEP_THING", "no DPV anchor"),
    "FundamentalRightsProtectionLevel": ("PARENT", "RiskAssessment"),
    "ConsistencyWithDelegatedActs":  ("KEEP_THING", "no DPV anchor"),

    # EU AI Act Art.10 - data requirements
    "DataBias":                      ("DUPLICATE", "DataBias"),

    # EU AI Act Art.11 - technical documentation
    "ProductRelatedToUnionHarmonisationLegislation": ("KEEP_THING", "no DPV anchor"),
    "AnnexAmendment":                ("KEEP_THING", "no DPV anchor"),

    # EU AI Act Art.13 - transparency
    "AppropriateTransparency":       ("PARENT",    "Obligation"),
    "HighRiskAISystemTransparency":  ("PARENT",    "Obligation"),
    "AIOutputExplanation":           ("KEEP_THING", "no DPV anchor"),

    # EU AI Act Art.14 - human oversight
    "HighRiskAISystemOverride":      ("KEEP_THING", "no DPV anchor"),

    # EU AI Act Art.15 - accuracy and robustness
    "Accuracy":                      ("KEEP_THING", "no DPV anchor"),
    "Robustness":                    ("KEEP_THING", "no DPV anchor"),

    # EU AI Act Art.16 - provider obligations
    "ProviderObligations":           ("PARENT",    "Obligation"),
    "HighRiskAiSystemPackaging":     ("KEEP_THING", "no DPV anchor"),
    "HighRiskAISystemProviderObligations": ("PARENT", "Obligation"),
    "EUDeclarationOfConformity":     ("DUPLICATE", "EUDeclarationOfConformity"),
    "AccessibilityRequirement":      ("KEEP_THING", "no DPV anchor"),
    "HighRiskAISystemAccessibility": ("KEEP_THING", "no DPV anchor"),

    # EU AI Act Art.20 - corrective actions
    "SystemWithdrawal":              ("KEEP_THING", "no DPV anchor"),
    "SystemDisabling":               ("KEEP_THING", "no DPV anchor"),
    "SystemRecall":                  ("KEEP_THING", "no DPV anchor"),

    # EU AI Act Art.21
    "CompetentAuthorityRequest":     ("PARENT",    "NationalCompetentAuthority"),

    # EU AI Act Art.26 - deployer obligations
    "DeployersObligations":          ("PARENT",    "Obligation"),
    "InputDataRelevance":            ("KEEP_THING", "no DPV anchor"),
    "InputDataRepresentativeness":   ("KEEP_THING", "no DPV anchor"),
    "PublicAuthorityDeployer":       ("KEEP_THING", "no DPV anchor"),
    "UnionInstitutionDeployer":      ("KEEP_THING", "no DPV anchor"),
    "PostRemoteBiometricIdentification": ("KEEP_THING", "no DPV anchor"),
    "AdverseLegalEffect":            ("KEEP_THING", "no DPV anchor"),

    # EU AI Act Art.29 - conformity assessment bodies
    "NotificationApplication":       ("PARENT",    "Notification"),
    "DesignationUnderUnionLegislation": ("KEEP_THING", "no DPV anchor"),

    # EU AI Act Art.50 - transparency for users
    "AccessibilityRequirements":     ("KEEP_THING", "no DPV anchor"),
    "FirstInteractionExposure":      ("KEEP_THING", "no DPV anchor"),
    "TransparencyObligationImplementation": ("PARENT", "Obligation"),

    # EU AI Act Art.51 - GPAI systemic risk
    "ThresholdAmendment":            ("KEEP_THING", "no DPV anchor"),

    # EU AI Act Art.52 - GPAI transparency
    "ReasonedRequest":               ("KEEP_THING", "no DPV anchor"),

    # EU AI Act Art.53 - GPAI obligations
    "AiModelLimitation":             ("KEEP_THING", "no DPV anchor"),
    "GeneralPurposeAiModelTrainingDataSummary": ("KEEP_THING", "no DPV anchor"),
    "AiOfficeTemplate":              ("KEEP_THING", "no DPV anchor"),
    "AlternativeMeansOfCompliance":  ("KEEP_THING", "no DPV anchor"),

    # EU AI Act Annex III
    "AIforEducation":                ("PARENT",    "Purpose"),
    "FinancialFraudDetectionExemption": ("KEEP_THING", "no DPV anchor"),

    # EU AI Act Annex IV
    "SoftwareVersion":               ("KEEP_THING", "no DPV anchor"),
    "FirmwareVersion":               ("KEEP_THING", "no DPV anchor"),
    "VersionUpdateRequirement":      ("PARENT",    "Obligation"),
    "SoftwarePackage":               ("KEEP_THING", "no DPV anchor"),
    "Marking":                       ("KEEP_THING", "no DPV anchor"),
    "AccuracyDegree":                ("KEEP_THING", "no DPV anchor"),
    "RiskToFundamentalRights":       ("PARENT",    "RiskAssessment"),
    "SystemLifecycleChanges":        ("KEEP_THING", "no DPV anchor"),

    # UK MDR 2002 Reg.2 - definitions
    "CoronavirusTestDevice":         ("KEEP_THING", "medical device specific, no DPV anchor"),
    "DeviceForPerformanceEvaluation": ("KEEP_THING", "medical device specific, no DPV anchor"),
    "PlacingOnTheMarket":            ("KEEP_THING", "medical device specific, no DPV anchor"),

    # UK MDR 2002 Reg.5 - Part II interpretation
    "CustomMadeDevice":              ("KEEP_THING", "medical device specific, no DPV anchor"),
    "RelevantDevice":                ("KEEP_THING", "medical device specific, no DPV anchor"),
    "SystemOrProcedurePack":         ("KEEP_THING", "medical device specific, no DPV anchor"),
    "SingleUseCombinationProduct":   ("KEEP_THING", "medical device specific, no DPV anchor"),
    "System":                        ("KEEP_THING", "too generic without more specific anchor"),

    # UK MDR 2002 Reg.7 - classification
    "MedicalDeviceClassification":   ("KEEP_THING", "medical device specific, no DPV anchor"),
    "GeneralMedicalDevice":          ("KEEP_THING", "medical device specific, no DPV anchor"),
    "DeviceClassificationDispute":   ("KEEP_THING", "medical device specific, no DPV anchor"),
    "ClassificationCriteria":        ("KEEP_THING", "medical device specific, no DPV anchor"),
    "SecretaryOfStateDetermination": ("KEEP_THING", "UK regulatory authority action, no DPV anchor"),

    # UK MDR 2002 Reg.8/9 - essential requirements
    "EssentialRequirements":         ("KEEP_THING", "medical device regulatory concept, no DPV anchor"),
    "ApplicableRequirements":        ("KEEP_THING", "medical device regulatory concept, no DPV anchor"),
    "DeviceSupply":                  ("KEEP_THING", "medical device specific, no DPV anchor"),
    "Regulation7222012":             ("KEEP_THING", "specific SI reference, no DPV anchor"),
    "RelevantEssentialRequirements": ("KEEP_THING", "medical device regulatory concept, no DPV anchor"),
    "PatientPrescription":           ("KEEP_THING", "medical device specific, no DPV anchor"),
    "ClassIIaDevice":                ("KEEP_THING", "medical device classification, no DPV anchor"),
    "ClassIIbDevice":                ("KEEP_THING", "medical device classification, no DPV anchor"),
    "ClassIIIDevice":                ("KEEP_THING", "medical device classification, no DPV anchor"),
    "AnnexVIIIConditions":           ("KEEP_THING", "UK MDR annex reference, no DPV anchor"),
    "EssentialRequirementsCompliance": ("PARENT",  "ComplianceAssessment"),
    "MedicinalProduct":              ("KEEP_THING", "medical regulatory specific, no DPV anchor"),
    "PersonalProtectiveEquipment":   ("KEEP_THING", "medical device specific, no DPV anchor"),

    # UK MDR 2002 Part 4A - post-market surveillance
    "FieldSafetyCorrectiveAction":   ("KEEP_THING", "medical device specific, no DPV anchor"),
    "PostMarketSurveillance":        ("KEEP_THING", "medical device regulatory concept, no DPV anchor"),
    "RegulatoryExemption":           ("KEEP_THING", "no DPV anchor"),
    "Device":                        ("KEEP_THING", "too generic, medical device specific context"),
    "PostMarketSurveillanceNotificationReview": ("KEEP_THING", "medical device specific, no DPV anchor"),
    "PostMarketSurveillanceInvestigation": ("KEEP_THING", "medical device specific, no DPV anchor"),
    "ManufacturerCooperation":       ("KEEP_THING", "no DPV anchor"),
    "TimelyResponse":                ("KEEP_THING", "no DPV anchor"),
    "DeviceAlterationRestriction":   ("KEEP_THING", "medical device specific, no DPV anchor"),
    "AnnexIIDevice":                 ("KEEP_THING", "UK MDR specific, no DPV anchor"),
    "WorkingDayResponseTime":        ("KEEP_THING", "no DPV anchor"),
    "RequestForPostMarketSurveillanceInformation": ("KEEP_THING", "medical device specific, no DPV anchor"),
    "TimeframeForProvidingPostMarketSurveillanceInformation": ("KEEP_THING", "medical device specific, no DPV anchor"),
    "PostMarketSurveillanceTask":    ("KEEP_THING", "medical device specific, no DPV anchor"),
    "ApprovedBodyDesignation":       ("KEEP_THING", "medical device regulatory concept, no DPV anchor"),
    "TaskVariation":                 ("KEEP_THING", "no DPV anchor"),
    "DesignationRestriction":        ("KEEP_THING", "no DPV anchor"),
    "DesignationWithdrawal":         ("KEEP_THING", "no DPV anchor"),
    "ApplicableCriteria":            ("KEEP_THING", "no DPV anchor"),

    # EU MDR 2017/745 Art.10 - manufacturer obligations
    "DeviceDesignChange":            ("KEEP_THING", "medical device specific, no DPV anchor"),
    "ConformityDeclaration":         ("KEEP_THING", "medical device regulatory concept, no DPV anchor"),
    "PostMarketClinicalFollowUp":    ("KEEP_THING", "medical device specific, no DPV anchor"),
    "DeviceCharacteristicChange":    ("KEEP_THING", "medical device specific, no DPV anchor"),
    "HarmonisedStandardsChange":     ("KEEP_THING", "medical device regulatory concept, no DPV anchor"),
    "ManufacturerObligations":       ("PARENT",    "Obligation"),
    "DeviceLabelInformation":        ("KEEP_THING", "medical device specific, no DPV anchor"),
    "MemberStateLanguageDetermination": ("KEEP_THING", "no DPV anchor"),
    "DeviceDocumentation":           ("KEEP_THING", "medical device specific, no DPV anchor"),
    "DeviceRestriction":             ("KEEP_THING", "medical device specific, no DPV anchor"),

    # EU MDR 2017/745 Art.61 - clinical evaluation
    "ClinicalInvestigationExemption": ("KEEP_THING", "medical device specific, no DPV anchor"),
    "ProductSpecificCS":             ("KEEP_THING", "medical device specific, no DPV anchor"),
    "Suture":                        ("KEEP_THING", "medical device specific product, no DPV anchor"),
    "Staple":                        ("KEEP_THING", "medical device specific product, no DPV anchor"),
    "DentalFilling":                 ("KEEP_THING", "medical device specific product, no DPV anchor"),
    "DentalBrace":                   ("KEEP_THING", "medical device specific product, no DPV anchor"),
    "ToothCrown":                    ("KEEP_THING", "medical device specific product, no DPV anchor"),
    "ImplementingActs":              ("KEEP_THING", "regulatory instrument concept, no DPV anchor"),
    "AnnexXIV":                      ("KEEP_THING", "EU MDR annex reference, no DPV anchor"),

    # EU MDR 2017/745 Annex I §17 - software requirements
    "VaryingEnvironment":            ("KEEP_THING", "no DPV anchor"),
    "UnauthorisedAccessProtection":  ("KEEP_THING", "no DPV anchor"),

    # EU MDR 2017/745 Annex VIII Rule 11 - software classification
    "ClassIIaSoftware":              ("KEEP_THING", "medical device classification, no DPV anchor"),
    "ClassIIbSoftware":              ("KEEP_THING", "medical device classification, no DPV anchor"),
    "ClassIIIsoftware":              ("KEEP_THING", "medical device classification, no DPV anchor"),

    # DUAA 2025 s.80 - automated decision-making
    "ControllerIntervention":        ("KEEP_THING", "Art.22C specific concept, no DPV anchor"),
    "HumanInvolvementRegulation":    ("KEEP_THING", "Art.22D regulatory power concept, no DPV anchor"),
    "AdditionalSafeguardMeasure":    ("KEEP_THING", "Art.22D specific concept, no DPV anchor"),
    "SupplementalSafeguardRequirements": ("KEEP_THING", "Art.22D specific concept, no DPV anchor"),
    "RegulationAmendmentRestriction": ("KEEP_THING", "Art.22D specific concept, no DPV anchor"),
    "AutomatedDecisionMakingRegulation": ("PARENT", "AutomatedDecisionMaking"),

    # DUAA 2025 Schedule 6 - transparency amendments
    "Article22CRequirement":         ("KEEP_THING", "DUAA Schedule 6 specific concept, no DPV anchor"),
}

# the 3 dedup pairs flagged by step 5 are all false positives:
# ApplicableCriteria vs BodyCriteriaAssessment - different concepts (criteria set vs assessment body)
# FinancialInstitutionInternalGovernance vs FinancialInstitutionGovernance - distinct granularity
# Suture vs Staple - completely different medical device products
# so MERGES is intentionally empty for this run
MERGES = {}

# hasLegalBasis restrictions grounded in literal GDPR Art.6(1) and Art.9(2) text
# these are kept from the design - if the class names don't appear in the current
# run (the LLM may have used different names), the cleanup script skips them silently
RESTRICTIONS = {
    "LegitimateInterest":          "A6-1-f",
    "VitalInterests":              "A6-1-d",
    "PublicInterest":              "A6-1-e",
    "PreventiveMedicine":          "A9-2-h",
    "OccupationalMedicine":        "A9-2-h",
    "HealthDataProcessingPurpose": "A9-2-h",
    "PublicHealthInterest":        "A9-2-i",
    "PublicHealthPurpose":         "A9-2-i",
}


# loads all DPV modules; Path.as_uri() produces correct file:/// URIs on Windows and Linux
def load_dpv():
    print("Loading DPV...")
    for p in DPV_MODULES:
        if not os.path.exists(p):
            sys.exit(f"DPV module not found: {p}")
        # get_ontology(Path(p).resolve().as_uri()).load()
        get_ontology(p).load()
    total = len(list(default_world.classes()))
    print(f"  {total} classes\n")
    return {c.name: c for c in default_world.classes()}


def resolve_chain(name, removed_redirect, seen=None):
    seen = seen or set()
    if name in seen:
        raise RuntimeError(f"cycle resolving {name}")
    seen.add(name)
    if name in removed_redirect:
        tgt = removed_redirect[name]
        if tgt.startswith(FALLRISK_NS):
            local = tgt[len(FALLRISK_NS):]
            if local in removed_redirect:
                return resolve_chain(local, removed_redirect, seen)
        return tgt
    return None


def main():
    t0 = time.time()
    real_dpv  = load_dpv()
    all_props = {p.name: p for p in default_world.search(type=ObjectProperty)}

    with open(ALIGNMENT_JSON, encoding="utf-8") as f:
        aligned = json.load(f)
    with open(CLASSES_JSON, encoding="utf-8") as f:
        created = json.load(f)

    align_by_name = {}
    for a in aligned:
        n = a.get("candidate_name")
        if n and n not in align_by_name:
            align_by_name[n] = a

    live = [c for c in created if not c.get("merged_into")]
    print(f"{len(live)} live classes\n")

    # build the redirect map for classes being removed
    removed_redirect = {}
    for name, (action, target) in AUDIT_DECISIONS.items():
        if action == "DUPLICATE":
            if target not in real_dpv:
                print(f"  [skip] not in DPV: {target}")
                continue
            removed_redirect[name] = real_dpv[target].iri
    for src, canonical in MERGES.items():
        if canonical in real_dpv:
            removed_redirect[src] = real_dpv[canonical].iri
        else:
            removed_redirect[src] = FALLRISK_NS + canonical

    # resolve final parent IRI for each class that survives
    final_parent = {}
    for c in live:
        name = c["name"]
        if name in removed_redirect:
            continue
        if name in AUDIT_DECISIONS:
            action, target = AUDIT_DECISIONS[name]
            if action == "PARENT":
                final_parent[name] = (real_dpv[target].iri if target in real_dpv
                                      else "http://www.w3.org/2002/07/owl#Thing")
            else:
                final_parent[name] = "http://www.w3.org/2002/07/owl#Thing"
        else:
            pu = c.get("parent_used", "")
            if pu.startswith(FALLRISK_NS):
                local = pu[len(FALLRISK_NS):]
                if local in removed_redirect:
                    redirected = resolve_chain(local, removed_redirect)
                    final_parent[name] = redirected
                    print(f"  cascade: {name} -> {redirected.split('#')[-1]}")
                else:
                    final_parent[name] = pu
            else:
                final_parent[name] = pu

    surviving = len(live) - len(removed_redirect)
    n_thing   = sum(1 for v in final_parent.values() if v.endswith("#Thing"))
    print(f"{len(live)} live -> {len(removed_redirect)} removed -> {surviving} surviving")
    print(f"owl:Thing: {n_thing}  |  real parent: {surviving - n_thing}\n")

    # rebuild ontology with corrected parents (two-pass for local references)
    onto        = get_ontology(FALLRISK_NS)
    new_classes = {}
    with onto:
        for c in live:
            name = c["name"]
            if name in removed_redirect:
                continue
            a       = align_by_name.get(name, {})
            new_cls = types.new_class(name, (Thing,))
            new_cls.label   = [a.get("definition", name)]
            new_cls.comment = [
                f"Source: {a.get('source_regulation','?')} — "
                f"{a.get('source_article_reference','?')} "
                f"(chunk {c['source_chunk_id']})"
            ]
            new_classes[name] = new_cls

    fixed = 0
    for name, cls in new_classes.items():
        tgt = final_parent[name]
        if tgt.endswith("#Thing"):
            continue
        if tgt.startswith(FALLRISK_NS):
            parent_cls = new_classes.get(tgt[len(FALLRISK_NS):])
        else:
            parent_cls = IRIS[tgt]
        if parent_cls is None:
            print(f"  [warn] could not resolve parent for {name}")
            continue
        cls.is_a = [parent_cls]
        fixed += 1
    print(f"pass 1: {len(new_classes)} classes  |  pass 2: {fixed} parented\n")

    # apply hasLegalBasis restrictions
    has_lb = IRIS["https://w3id.org/dpv/owl#hasLegalBasis"]
    if has_lb is None:
        print("[warn] dpv:hasLegalBasis not found, skipping restrictions")
    else:
        applied = 0
        for cand_name, lb_local in RESTRICTIONS.items():
            lb_cls = real_dpv.get(lb_local)
            if lb_cls is None:
                continue
            if cand_name in removed_redirect:
                tgt_iri    = resolve_chain(cand_name, removed_redirect) or removed_redirect[cand_name]
                target_cls = IRIS[tgt_iri]
            else:
                target_cls = new_classes.get(cand_name)
            if target_cls is None:
                continue
            with onto:
                target_cls.is_a.append(has_lb.some(lb_cls))
            applied += 1
            print(f"  + {cand_name} — hasLegalBasis some {lb_local}")
        print(f"\n{applied}/{len(RESTRICTIONS)} restrictions applied\n")

    # run HermiT and exit on failure
    print("Running HermiT...")
    t_r = time.time()
    with onto:
        sync_reasoner_hermit(infer_property_values=False)
    inconsistent = list(default_world.inconsistent_classes())
    print(f"  {'PASS' if not inconsistent else 'FAIL'} — "
          f"{len(inconsistent)} unsatisfiable  ({time.time()-t_r:.1f}s)\n")
    if inconsistent:
        for ic in inconsistent:
            print(f"  UNSAT: {ic}")
        sys.exit(1)

    # serialize to RDF/XML
    print(f"Serializing to {OUT_RDF} ...")
    tmp = OUT_RDF + ".nt"
    onto.save(file=tmp, format="ntriples")
    g = rdflib.Graph()
    g.parse(tmp, format="nt")
    g.bind("fallrisk", rdflib.Namespace(FALLRISK_NS))
    g.bind("dpv",      rdflib.Namespace("https://w3id.org/dpv/owl#"))
    g.bind("dpv-pd",   rdflib.Namespace("https://w3id.org/dpv/pd/owl#"))
    g.bind("dpv-risk", rdflib.Namespace("https://w3id.org/dpv/risk/owl#"))
    g.bind("dpv-ai",   rdflib.Namespace("https://w3id.org/dpv/ai/owl#"))
    g.bind("gdpr",     rdflib.Namespace("https://w3id.org/dpv/legal/eu/gdpr/owl#"))
    g.bind("aiact",    rdflib.Namespace("https://w3id.org/dpv/legal/eu/aiact/owl#"))
    g.serialize(destination=OUT_RDF, format="xml")
    os.remove(tmp)
    print(f"  {len(g)} triples\n")

    # write updated classes_created_v2.json
    final_created = []
    dup_names = {n for n, (a, _) in AUDIT_DECISIONS.items() if a == "DUPLICATE"}
    for c in live:
        name = c["name"]
        if name in removed_redirect:
            final_created.append({
                "name": name, "merged_into": removed_redirect[name],
                "merge_reason": "duplicate_of_existing_dpv" if name in dup_names else "dedup_merge",
                "parent_used": None, "source_chunk_id": c["source_chunk_id"],
            })
        else:
            final_created.append({
                "name":            name,
                "merged_into":     None,
                "parent_used":     final_parent[name],
                "parent_resolved": not final_parent[name].endswith("#Thing"),
                "source_chunk_id": c["source_chunk_id"],
                "has_restriction": name in RESTRICTIONS,
            })
    with open(OUT_CLASSES_V2, "w", encoding="utf-8") as f:
        json.dump(final_created, f, indent=2, ensure_ascii=False)

    s_count  = sum(1 for x in final_created if not x["merged_into"])
    rm_count = len(final_created) - s_count
    th_count = sum(1 for x in final_created if not x["merged_into"] and not x.get("parent_resolved", True))
    rs_count = sum(1 for x in final_created if x.get("has_restriction"))

    with open(OUT_LOG, "w", encoding="utf-8") as f:
        f.write(f"""# Phase 1 Cleanup Log

- Surviving : {s_count}
- owl:Thing  : {th_count}
- Removed    : {rm_count}
- Restricted : {rs_count}
- Triples    : {len(g)}
- Reasoner   : {'PASS' if not inconsistent else 'FAIL'}
- Output     : {OUT_RDF}
""")

    print(f"done in {time.time()-t0:.1f}s")
    print(f"surviving: {s_count}  |  Thing: {th_count}  |  removed: {rm_count}  |  restricted: {rs_count}")
    print(f"output: {OUT_RDF}")
    print("\nPhase 1 complete — open dpv-fallrisk-ext-v2.rdf in Protege")


if __name__ == "__main__":
    main()