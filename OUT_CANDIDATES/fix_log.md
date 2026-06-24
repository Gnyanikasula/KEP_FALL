# Phase 1 Fix Log  (v2 → v3)

- Input v1 (restrictions source) : D:\KEP_FALL\KEP_FALL\OUT_CANDIDATES\dpv-fallrisk-ext.rdf
- Input v2 (hierarchy source)    : D:\KEP_FALL\KEP_FALL\OUT_CANDIDATES\dpv-fallrisk-ext-v2.rdf
- Output v3                      : D:\KEP_FALL\KEP_FALL\OUT_CANDIDATES\dpv-fallrisk-ext-v3.rdf

## Counts
- KEP classes          : 627  (621 from v2  +  6 domain classes)
- OWL restrictions     : 68  (62 ported from v1,  domain class restrictions extra)
- Object properties    : 13  (declared with domain + range)
- Total triples        : 2833
- Reasoner             : PASS

## Domain classes added
- FallRiskPrediction
- FallRiskScore
- AccelerometerReading
- GaitAnalysisOutput
- WearableSensor
- WearableDataProcessing

## Object properties declared
- hasPersonalData
- hasOrganisationalMeasure
- hasTechnicalOrganisationalMeasure
- hasRiskAssessment
- hasLegalBasis
- hasPurpose
- hasDataSubject
- hasRight
- hasObligation
- hasTechnicalMeasure
- hasNotice
- hasRisk
- isMitigatedByMeasure

## Time
- 26.8s

## Next step
Run phase1_llm_restrictions.py  →  v3 + LLM restriction pass  →  v4
