# Phase 1 LLM Restrictions Log  (v3 → v4)

## Stats
- Chunks processed      : 333
- Classes without restr : 560
- LLM proposed          : 666
- Applied               : 565
- Rejected (class)      : 0
- Rejected (property)   : 3
- Rejected (target)     : 98
- Duplicates skipped    : 0
- Total restrictions v4 : 633
- Total classes v4      : 627
- Total triples v4      : 5093
- Reasoner              : PASS
- Time                  : 1082.7s

## Applied restrictions
  - ArchivingPurpose → hasPurpose some IncompatibleProcessing
    Rationale: Further processing for archiving purposes in the public interest shall not be considered to be incompatible with the initial purposes.
  - HistoricalResearchPurpose → hasPurpose some IncompatibleProcessing
    Rationale: Further processing for historical research purposes shall not be considered to be incompatible with the initial purposes.
  - IncompatibleProcessing → hasLegalBasis some ArchivingPurpose
    Rationale: Further processing for archiving purposes in the public interest shall, in accordance with Article 89(1), not be considered to be incompatible with the initial purposes.
  - IncompatibleProcessing → hasLegalBasis some HistoricalResearchPurpose
    Rationale: Further processing for historical research purposes shall, in accordance with Article 89(1), not be considered to be incompatible with the initial purposes.
  - SecurityOfPersonalData → hasTechnicalOrganisationalMeasure some DataSecurityManagement
    Rationale: The text mentions 'using appropriate technical or organisational measures' to ensure integrity and confidentiality.
  - SecurityOfPersonalData → hasRiskAssessment some RiskAssessment
    Rationale: The text implies a need for assessing risks to ensure 'integrity and confidentiality'.
  - ConsentForSpecificPurpose → hasLegalBasis some LawfulAIExceptions
    Rationale: Article 6(1)(a) states that processing is lawful if the data subject has given consent to the processing of his or her personal data for one or more specific purposes.
  - ContractualObligations → hasLegalBasis some UnionLawException
    Rationale: Article 6(1)(b) mentions processing necessary for contract performance.
  - VitalInterest → hasLegalBasis some Processing
    Rationale: GDPR, Article 6(1) — Lawfulness of processing(d) states that processing is lawful if necessary to protect vital interests.
  - ProcessingForPublicAuthorities → hasLegalBasis some UnionLawException
    Rationale: Point (f) of the first subparagraph shall not apply to processing carried out by public authorities in the performance of their tasks.
  - LawfulAndFairProcessing → hasLegalBasis some UnionLawException
    Rationale: Member States may maintain or introduce more specific provisions to adapt the application of the rules of this Regulation.
  - LawfulAndFairProcessing → hasObligation some TransparencyObligation
    Rationale: ensuring lawful and fair processing including for other specific processing situations
  - LawfulAndFairProcessing → hasTechnicalOrganisationalMeasure some DataSecurityManagement
    Rationale: ensuring lawful and fair processing
  - MemberStateLaw → hasLegalBasis some UnionLawException
    Rationale: The regulatory text mentions 'Union or the Member State law shall meet an objective of public interest'.
  - MemberStateLaw → hasPurpose some PublicInterestObjective
    Rationale: The regulatory text states 'The purpose of the processing shall be determined in that legal basis' and 'shall meet an objective of public interest'.
  - PurposeLink → hasLegalBasis some UnionLawException
    Rationale: The text mentions 'on a Union or Member State law which constitutes a necessary and proportionate measure in a democratic society'.
  - CriminalConvictionsAndOffencesProcessing → hasPersonalData some SpecialCategoryPersonalData
    Rationale: The text mentions 'special categories of personal data' in Article 9.
  - FurtherProcessingConsequence → hasRiskAssessment some RiskAssessment
    Rationale: The text mentions 'the possible consequences of the intended further processing for data subjects' implying a risk assessment.
  - AppropriateSafeguard → hasTechnicalOrganisationalMeasure some Encryption
    Rationale: The text mentions 'encryption or pseudonymisation' as examples of appropriate safeguards.
  - AppropriateSafeguard → hasTechnicalOrganisationalMeasure some Pseudonymisation
    Rationale: The text mentions 'encryption or pseudonymisation' as examples of appropriate safeguards.
  - ConsentDemonstration → hasLegalBasis some ConsentDemonstration
    Rationale: The controller shall be able to demonstrate that the data subject has consented to processing of his or her personal data.
  - UnionLawException → hasLegalBasis some ExplicitConsent
    Rationale: The regulatory text states that paragraph 1 shall not apply if Union or Member State law provide that the prohibition referred to in paragraph 1 may not be lifted by the data subject.
  - ExplicitConsent → hasLegalBasis some UnionLawException
    Rationale: The regulatory text states that the data subject has given explicit consent to the processing of those personal data for one or more specified purposes, except where Union or Member State law provide that the prohibition referred to in paragraph 1 may not be lifted by the data subject.
  - SocialProtectionLawObligation → hasLegalBasis some UnionLawException
    Rationale: The regulatory text mentions 'authorised by Union or Member State law'.
  - UnionLawSecrecy → hasLegalBasis some UnionLawException
    Rationale: Personal data may be processed when subject to Union law obligation of professional secrecy.
  - MemberStateLawSecrecy → hasLegalBasis some UnionLawException
    Rationale: Personal data may be processed when subject to Member State law obligation of professional secrecy.
  - ThirdCountryTransfer → hasLegalBasis some AdequacyDecision
    Rationale: The controller intends to transfer personal data to a third country or international organisation and the existence or absence of an adequacy decision by the Commission.
  - ThirdCountryTransfer → hasNotice some TransparencyObligation
    Rationale: The controller shall provide the data subject with information about the transfer, including the existence or absence of an adequacy decision.
  - RightToRestrictionOfProcessing → hasRight some RightOfAccess
    Rationale: The controller shall provide the data subject with the right to request from the controller access to and rectification or erasure of personal data or restriction of processing concerning the data subject.
  - RightToRestrictionOfProcessing → hasRight some RightToRequestAccess
    Rationale: The controller shall provide the data subject with the right to request from the controller access to and rectification or erasure of personal data or restriction of processing concerning the data subject.
  - ConsentWithdrawalNotice → hasRight some RightOfAccess
    Rationale: The controller shall provide the data subject with the existence of the right to withdraw consent at any time.
  - LawfulnessBeforeWithdrawal → hasLegalBasis some ExplicitConsentBasedDecision
    Rationale: The processing based on consent before its withdrawal is lawful.
  - AdditionalInformationForFurtherProcessing → hasPurpose some FurtherProcessingConsequence
    Rationale: The controller shall provide the data subject prior to further processing with information on that other purpose.
  - RightToRequestAccess → hasRight some RightOfAccess
    Rationale: The text mentions 'the right to request from the controller access to and rectification or erasure of personal data'.
  - RightToRequestRectification → hasRight some RightOfAccess
    Rationale: The text mentions 'the right to request from the controller access to and rectification or erasure of personal data'.
  - RightToRequestErasure → hasRight some RightOfAccess
    Rationale: The text mentions 'the right to request from the controller access to and rectification or erasure of personal data'.
  - RightToRequestRestrictionOfProcessing → hasRight some RightOfAccess
    Rationale: The text mentions 'the right to request from the controller access to and rectification or erasure of personal data or restriction of processing'.
  - RightToObjectToProcessing → hasRight some RightOfAccess
    Rationale: The text mentions 'the right to object to processing'.
  - LogicInvolved → hasObligation some TransparencyObligation
    Rationale: The controller shall provide the data subject with meaningful information about the logic involved.
  - LogicInvolved → hasPurpose some AutomatedDecisionMaking
    Rationale: The logic involved is used for automated decision-making.
  - MeaningfulInformation → hasObligation some TransparencyObligation
    Rationale: The controller shall provide the data subject with meaningful information.
  - MeaningfulInformation → hasPurpose some AutomatedDecisionMaking
    Rationale: Meaningful information is provided for automated decision-making.
  - ReasonablePeriod → hasLegalBasis some RegulatoryExemption
    Rationale: The controller shall provide the information within a reasonable period after obtaining the personal data, implying a legal basis for exemption.
  - ReasonablePeriod → hasObligation some TransparencyObligation
    Rationale: The controller shall provide the information referred to in paragraphs 1 and 2 within a reasonable period.
  - FirstDisclosure → hasLegalBasis some TransparencyObligation
    Rationale: The controller shall provide the information ... at the latest when the personal data are first disclosed.
  - PriorNotificationForFurtherProcessing → hasPurpose some FurtherProcessingConsequence
    Rationale: The controller shall provide the data subject prior to further processing with information on that other purpose.
  - DisproportionateEffort → hasLegalBasis some LawfulAIExceptions
    Rationale: Paragraphs 1 to 4 shall not apply where and insofar as: (b) the provision of such information proves impossible or would involve a disproportionate effort
  - DisproportionateEffort → hasPurpose some ProcessingRiskReassessment
    Rationale: processing for archiving purposes in the public interest, scientific or historical research purposes or statistical purposes
  - DisproportionateEffort → hasLegalBasis some RegulatoryExemption
    Rationale: subject to the conditions and safeguards referred to in Article 89(1) or in so far as the obligation referred to in paragraph 1 of this Article is likely to render impossible or seriously impair the achievement of the objectives of that processing
  - ProfessionalSecrecy → hasLegalBasis some UnionLawException
    Rationale: GDPR, Article 14(5)(d) mentions 'an obligation of professional secrecy regulated by Union or Member State law'.
  - StatutoryObligationOfSecrecy → hasLegalBasis some UnionLawException
    Rationale: GDPR, Article 14(5)(d) mentions 'an obligation of professional secrecy regulated by Union or Member State law, including a statutory obligation of secrecy'.
  - RightOfAccess → hasPurpose some RightOfAccess
    Rationale: The right of access by the data subject includes obtaining information on the purposes of the processing.
  - ThirdCountryRecipient → hasLegalBasis some RightOfAccess
    Rationale: The text mentions 'recipients in third countries' in relation to the right of access by the data subject.
  - Profiling → hasLegalBasis some AutomatedDecisionMaking
    Rationale: Article 15(1)(h) mentions 'the existence of automated decision-making, including profiling'.
  - DataTransferNotificationRight → hasRight some RightOfAccess
    Rationale: The data subject shall have the right to be informed of the appropriate safeguards pursuant to Article 46 relating to the transfer.
  - ElectronicForm → hasRight some RightOfAccess
    Rationale: The controller shall provide the information in a commonly used electronic form where the data subject makes the request by electronic means.
  - RightToErasureCommunication → hasPurpose some DataRestorability
    Rationale: The controller shall take reasonable steps to inform controllers which are processing the personal data that the data subject has requested the erasure.
  - PubliclyAvailablePersonalDataErasure → hasTechnicalMeasure some TransparencyObligation
    Rationale: The controller shall take reasonable steps, including technical measures, to inform controllers which are processing the personal data.
  - ControllerNotificationForErasure → hasObligation some SecurityOfPersonalData
    Rationale: The controller shall take reasonable steps, including technical measures, to inform controllers which are processing the personal data.
  - LegalObligationUnionLaw → hasLegalBasis some UnionLawException
    Rationale: The text mentions 'compliance with a legal obligation which requires processing by Union or Member State law'.
  - LegalObligationUnionLaw → hasPurpose some ComplianceDemonstration
    Rationale: The text implies that the purpose is for compliance with a legal obligation.
  - VerificationPeriod → hasPurpose some AccuracyDegree
    Rationale: The text mentions 'for a period enabling the controller to verify the accuracy of the personal data'.
  - UnlawfulProcessing → hasLegalBasis some RightOfAccess
    Rationale: The data subject opposes the erasure of personal data and requests restriction of use instead.
  - UnlawfulProcessing → hasRight some DataSubjectConsultation
    Rationale: The data subject has the right to obtain restriction of processing.
  - RestrictionForLegalClaims → hasLegalBasis some LegalClaim
    Rationale: The data subject requires the personal data for the establishment, exercise or defence of legal claims.
  - RestrictionLifting → hasNotice some DataSubjectConsultation
    Rationale: A data subject who has obtained restriction of processing pursuant to paragraph 1 shall be informed by the controller before the restriction of processing is lifted.
  - RestrictionOfProcessingNotification → hasLegalBasis some RightOfAccess
    Rationale: GDPR, Article 18(3) — Right to restriction of processing
  - RiskOfVaryingLikelihoodAndSeverity → hasRiskAssessment some RiskAssessment
    Rationale: The text mentions 'risks of varying likelihood and severity' and requires the controller to implement measures to meet the requirements of this Regulation.
  - RiskOfVaryingLikelihoodAndSeverity → isMitigatedByMeasure some RiskMitigationSafeguard
    Rationale: The text mentions 'implement appropriate technical and organisational measures' to mitigate risks.
  - RiskOfVaryingLikelihoodAndSeverity → hasTechnicalOrganisationalMeasure some PrivacyByDesign
    Rationale: The text mentions 'pseudonymisation' and 'integrate the necessary safeguards' which implies technical and organisational measures for privacy by design.
  - SubliminalTechnique → hasLegalBasis some ProhibitedBehaviourDetection
    Rationale: The use of subliminal techniques beyond a person's consciousness is prohibited.
  - MaterialDistortion → hasLegalBasis some BehaviouralDistortion
    Rationale: Materially distorting the behaviour of a person or a group of persons is prohibited.
  - InformedDecisionImpairment → hasLegalBasis some InformedDecisionImpairment
    Rationale: Impairing a person's ability to make an informed decision is prohibited.
  - SignificantHarm → hasLegalBasis some SignificantImpactAssessment
    Rationale: Causing significant harm to a person or a group of persons is prohibited.
  - BehaviouralDistortion → hasLegalBasis some ProhibitedBehaviourDetection
    Rationale: The text explicitly prohibits AI practices that cause significant harm by distorting behaviour.
  - BehaviouralDistortion → hasRisk some SignificantImpactAssessment
    Rationale: The text mentions the risk of significant harm to persons.
  - SocialBehaviourEvaluation → hasLegalBasis some ProhibitedBehaviourDetection
    Rationale: The text explicitly prohibits AI systems for the evaluation or classification of natural persons or groups of persons based on their social behaviour.
  - DetrimentalTreatment → hasLegalBasis some ProhibitedBehaviourDetection
    Rationale: The regulatory text explicitly prohibits certain AI practices, including targeted search for victims of abduction, trafficking, or sexual exploitation.
  - UnrelatedSocialContext → hasLegalBasis some CriminalOffenceVictim
    Rationale: The text mentions victims of abduction, trafficking in human beings or sexual exploitation of human beings.
  - UnjustifiedTreatment → hasLegalBasis some ProhibitedBehaviourDetection
    Rationale: The text explicitly prohibits certain AI practices, implying a legal basis for detecting prohibited behavior.
  - UnjustifiedTreatment → hasPurpose some CriminalActivityInvolvementAssessment
    Rationale: The text mentions prevention of substantial and imminent threat to life or physical safety, and genuine and present or foreseeable threat of a terrorist attack, which relates to assessing involvement in criminal activity.
  - ProfilingBasedRiskAssessment → hasPurpose some CriminalActivityInvolvementAssessment
    Rationale: The text states that AI systems for making risk assessments of natural persons to assess or predict the risk of committing a criminal offence based solely on profiling are prohibited.
  - ProfilingBasedRiskAssessment → hasRiskAssessment some RiskAssessment
    Rationale: The text mentions risk assessments of natural persons to assess or predict the risk of a natural person committing a criminal offence.
  - FacialRecognitionDatabase → hasLegalBasis some ProhibitedAIpractice
    Rationale: The text explicitly prohibits the creation or expansion of facial recognition databases through untargeted scraping of facial images.
  - UntargetedScraping → hasLegalBasis some ProhibitedAIpractice
    Rationale: The text explicitly prohibits untargeted scraping of facial images for creating or expanding facial recognition databases.
  - WorkplaceEmotionInference → hasLegalBasis some ProhibitedBehaviourDetection
    Rationale: The text explicitly prohibits the use of AI systems to infer emotions in the areas of workplace.
  - WorkplaceEmotionInference → hasPurpose some LawfulAIExceptions
    Rationale: The text mentions exceptions for medical or safety reasons.
  - MedicalEmotionInference → hasLegalBasis some MedicalDeviceClassification
    Rationale: The text allows for the use of AI systems for medical reasons.
  - BiometricCategorisation → hasLegalBasis some SpecialCategoryPersonalData
    Rationale: Biometric categorisation systems that categorise individually natural persons based on their biometric data to deduce or infer their race, political opinions, trade union membership, religious or philosophical beliefs, sex life or sexual orientation.
  - RacialBiometricCategorisation → hasLegalBasis some RacialOrEthnicOrigin
    Rationale: the placing on the market, the putting into service for this specific purpose, or the use of biometric categorisation systems that categorise individually natural persons based on their biometric data to deduce or infer their race
  - SexLifeOrSexualOrientationBiometricCategorisation → hasLegalBasis some SensitiveAttributeInference
    Rationale: the placing on the market, the putting into service for this specific purpose, or the use of biometric categorisation systems that categorise individually natural persons based on their biometric data to deduce or infer their sex life or sexual orientation
  - SafetyComponent → hasLegalBasis some UnionHarmonisationLegislation
    Rationale: The text mentions 'the Union harmonisation legislation listed in Annex I' as a condition for an AI system to be considered high-risk.
  - HighRiskAISystem → hasLegalBasis some UnionHarmonisationLegislation
    Rationale: The AI system is required to undergo a third-party conformity assessment pursuant to the Union harmonisation legislation listed in Annex I.
  - ClassificationRule → hasLegalBasis some AnnexIII
    Rationale: AI systems referred to in Annex III shall be considered to be high-risk.
  - PatternDetection → hasRisk some RiskAssessment
    Rationale: By derogation from paragraph 2, an AI system referred to in Annex III shall not be considered to be high-risk where it does not pose a significant risk of harm to the health, safety or fundamental rights of natural persons.
  - SignificantRiskOfHarm → hasRisk some HighRiskAISystem
    Rationale: An AI system referred to in Annex III shall not be considered to be high-risk where it does not pose a significant risk of harm.
  - SignificantRiskOfHarm → hasLegalBasis some AnnexIII
    Rationale: An AI system referred to in Annex III shall not be considered to be high-risk where it does not pose a significant risk of harm.
  - SignificantRiskOfHarm → hasRiskAssessment some RiskAssessment
    Rationale: the AI system does not materially influence the outcome of decision making.
  - DelegatedAct → hasLegalBasis some RegulationAmendmentRestriction
    Rationale: The Commission shall adopt delegated acts in accordance with Article 97 in order to amend paragraph 3, second subparagraph, of this Article.
  - ConcreteEvidence → hasRiskAssessment some RiskAssessment
    Rationale: there is concrete and reliable evidence that this is necessary to maintain the level of protection of health, safety and fundamental rights
  - FundamentalRightsProtectionLevel → hasLegalBasis some DelegatedActs
    Rationale: The text mentions 'consistency with the delegated acts adopted pursuant to Article 7(1)'.
  - ConsistencyWithDelegatedActs → hasLegalBasis some DelegatedActs
    Rationale: The text explicitly mentions 'delegated acts adopted pursuant to Article 7(1)'.
  - PostMarketMonitoringSystem → hasRiskAssessment some RiskAssessment
    Rationale: The risk management system shall comprise the evaluation of other risks possibly arising, based on the analysis of data gathered from the post-market monitoring system.
  - MitigatableRisk → isMitigatedByMeasure some RiskManagementMeasure
    Rationale: The text mentions that risks shall concern only those which may be reasonably mitigated or eliminated through the development or design of the high-risk AI system, or the provision of adequate technical information.
  - MitigatableRisk → hasRiskAssessment some RiskAssessment
    Rationale: The text implies that risks are assessed as part of the risk management system.
  - RequirementsCombination → hasRisk some RiskManagementSystem
    Rationale: The risk management measures referred to in paragraph 2, point (d), shall give due consideration to the effects and possible interaction resulting from the combined application of the requirements set out in this Section, with a view to minimising risks more effectively.
  - TechnicallyFeasibleRiskReduction → isMitigatedByMeasure some RiskManagementMeasure
    Rationale: The risk management measures referred to in paragraph 2, point (d), shall be such that the relevant residual risk associated with each hazard, as well as the overall residual risk of the high-risk AI systems is judged to be acceptable.
  - TechnicallyFeasibleRiskReduction → hasTechnicalMeasure some HighRiskAISystem
    Rationale: In identifying the most appropriate risk management measures, the following shall be ensured: (a) elimination or reduction of risks identified and evaluated pursuant to paragraph 2 in as far as technically feasible through adequate design and development of the high-risk AI system;
  - DeployersTraining → hasPurpose some RiskManagementSystem
    Rationale: The text mentions 'provision of information required pursuant to Article 13 and, where appropriate, training to deployers' which implies that deployers training has a purpose related to risk management system.
  - DeployersTraining → hasTechnicalMeasure some RiskAssessment
    Rationale: The text mentions 'due consideration shall be given to the technical knowledge, experience, education, the training to be expected by the deployer' which implies that deployers training is a technical measure related to risk assessment.
  - HighRiskAiSystemTesting → hasPurpose some RiskManagementSystem
    Rationale: Testing shall ensure that high-risk AI systems perform consistently for their intended purpose and that they are in compliance with the requirements set out in this Section.
  - HighRiskAiSystemTesting → hasRiskAssessment some RiskAssessment
    Rationale: High-risk AI systems shall be tested for the purpose of identifying the most appropriate and targeted risk management measures.
  - ConsistencyOfAiSystemPerformance → hasRisk some RiskManagementMeasure
    Rationale: Testing shall ensure that high-risk AI systems perform consistently for their intended purpose and that they are in compliance with the requirements set out in this Section.
  - ProbabilisticThreshold → hasPurpose some HighRiskAISystem
    Rationale: The text mentions 'probabilistic thresholds that are appropriate to the intended purpose of the high-risk AI system'.
  - DataGovernancePractice → hasPurpose some HighRiskAISystem
    Rationale: Training, validation and testing data sets shall be subject to data governance and management practices appropriate for the intended purpose of the high-risk AI system.
  - HighRiskAISystemDataGovernance → hasPurpose some DataSecurityManagement
    Rationale: Data governance and management practices shall be appropriate for the intended purpose of the high-risk AI system.
  - DataOrigin → hasRight some RightOfAccess
    Rationale: In the case of personal data, the original purpose of the data collection shall be considered.
  - TestingDataGovernance → hasTechnicalOrganisationalMeasure some PrivacyByDesign
    Rationale: Training, validation and testing data sets shall be subject to data governance and management practices.
  - DataPreparationProcessingOperation → hasPurpose some HighRiskAISystem
    Rationale: Training, validation and testing data sets shall be subject to data governance and management practices appropriate for the intended purpose of the high-risk AI system.
  - DataGovernanceAssessment → hasPurpose some HighRiskAISystem
    Rationale: The text mentions 'data governance and management practices appropriate for the intended purpose of the high-risk AI system'.
  - DataSetAvailabilityAssessment → hasPurpose some HighRiskAISystem
    Rationale: The text mentions 'an assessment of the availability, quantity and suitability of the data sets that are needed' for the high-risk AI system.
  - BiasExamination → hasRisk some DiscriminationRisk
    Rationale: The text mentions examination in view of possible biases that are likely to lead to discrimination prohibited under Union law.
  - BiasExamination → hasRisk some HealthRiskAssessment
    Rationale: The text mentions examination in view of possible biases that are likely to affect the health and safety of persons.
  - DataGap → hasRiskAssessment some RiskAssessment
    Rationale: The identification of relevant data gaps that prevent compliance with this Regulation implies a risk assessment.
  - DataShortcoming → hasRiskAssessment some RiskAssessment
    Rationale: The identification of shortcomings that prevent compliance with this Regulation implies a risk assessment.
  - RepresentativenessOfData → hasTechnicalMeasure some DataSecurityManagement
    Rationale: Data sets shall be sufficiently representative.
  - RepresentativenessOfData → hasPurpose some HighRiskAISystem
    Rationale: Data sets shall have appropriate statistical properties in view of the intended purpose.
  - CompletenessOfData → hasTechnicalMeasure some DataSecurityManagement
    Rationale: Data sets shall be free of errors and complete.
  - GeographicalSetting → hasPurpose some HighRiskAISystem
    Rationale: Data sets shall take into account, to the extent required by the intended purpose, the characteristics or elements that are particular to the specific geographical, contextual, behavioural or functional setting within which the high-risk AI system is intended to be used.
  - ContextualSetting → hasPurpose some HighRiskAISystem
    Rationale: Data sets shall take into account, to the extent required by the intended purpose, the characteristics or elements that are particular to the specific geographical, contextual, behavioural or functional setting within which the high-risk AI system is intended to be used.
  - FunctionalSetting → hasPurpose some HighRiskAISystem
    Rationale: Data sets shall take into account, to the extent required by the intended purpose, the characteristics or elements that are particular to the specific geographical, contextual, behavioural or functional setting within which the high-risk AI system is intended to be used.
  - BiasDetectionCorrection → hasPersonalData some SpecialCategoryPersonalData
    Rationale: The text explicitly mentions processing special categories of personal data for bias detection and correction.
  - PseudonymisationForBiasCorrection → hasTechnicalMeasure some Pseudonymisation
    Rationale: The text mentions 'pseudonymisation' as a state-of-the-art security and privacy-preserving measure.
  - PseudonymisationForBiasCorrection → hasPurpose some BiasDetectionCorrection
    Rationale: The text mentions that pseudonymisation is used for bias detection and correction.
  - PseudonymisationForBiasCorrection → hasPersonalData some SpecialCategoryPersonalData
    Rationale: The text mentions that special categories of personal data are subject to pseudonymisation.
  - SpecialCategoryDataProcessingCondition → hasTechnicalOrganisationalMeasure some DataSecurityManagement
    Rationale: The text mentions 'measures to ensure that the personal data processed are secured, protected, subject to suitable safeguards, including strict controls and documentation of the access'.
  - SpecialCategoryDataProcessingCondition → hasTechnicalOrganisationalMeasure some PrivacyByDesign
    Rationale: The text mentions 'measures to ensure that the personal data processed are secured, protected, subject to suitable safeguards'.
  - SpecialCategoryDataProcessingCondition → hasTechnicalOrganisationalMeasure some PrivacyByDefault
    Rationale: The text mentions 'measures to ensure that the personal data processed are secured, protected, subject to suitable safeguards'.
  - SpecialCategoryDataProcessingRestriction → hasPurpose some BiasDetectionCorrection
    Rationale: The text states that processing of special categories of personal data is allowed for the purpose of ensuring bias detection and correction.
  - SpecialCategoryDataProcessingRestriction → hasLegalBasis some LawfulAIExceptions
    Rationale: The text mentions that the processing must be subject to appropriate safeguards and in accordance with Regulations (EU) 2016/679 and (EU) 2018/1725 and Directive (EU) 2016/680.
  - SpecialCategoriesDataProcessingReason → hasLegalBasis some LawfulAIExceptions
    Rationale: The text mentions 'subject to appropriate safeguards for the fundamental rights and freedoms of natural persons' and references Regulations (EU) 2016/679 and (EU) 2018/1725 and Directive (EU) 2016/680.
  - TechnicalDocumentation → hasLegalBasis some HighRiskAISystem
    Rationale: The technical documentation shall demonstrate that the high-risk AI system complies with the requirements set out in this Section.
  - SimplifiedTechnicalDocumentation → hasLegalBasis some SME
    Rationale: SMEs, including start-ups, may provide the elements of the technical documentation specified in Annex IV in a simplified manner.
  - NotifiedBody → hasObligation some ConformityAssessmentProcedure
    Rationale: Notified bodies shall accept the form for the purposes of the conformity assessment.
  - NationalCompetentAuthority → hasRight some HighRiskAISystem
    Rationale: to assess the compliance of the AI system with those requirements.
  - ProductRelatedToUnionHarmonisationLegislation → hasLegalBasis some UnionHarmonisationLegislation
    Rationale: The regulatory text mentions 'Union harmonisation legislation listed in Section A of Annex I'.
  - AnnexAmendment → hasLegalBasis some DelegatedActs
    Rationale: The Commission is empowered to adopt delegated acts in accordance with Article 97.
  - SystemLifetimeLogging → hasTechnicalMeasure some HighRiskAISystemLoggingCapability
    Rationale: High-risk AI systems shall technically allow for the automatic recording of events (logs) over the lifetime of the system.
  - LoggingCapability → hasPurpose some PostMarketSurveillance
    Rationale: Logging capabilities shall enable the recording of events relevant for facilitating the post-market monitoring.
  - RecordedEvent → hasLegalBasis some PostMarketMonitoring
    Rationale: Events relevant for facilitating the post-market monitoring referred to in Article 72 shall be recorded.
  - HighRiskAISystemLogging → hasPurpose some HighRiskAISystemTransparency
    Rationale: Logging capabilities shall enable the recording of events relevant for monitoring the operation of high-risk AI systems.
  - HighRiskAISystemLogging → hasTechnicalMeasure some HighRiskAISystemLogRetention
    Rationale: Logging capabilities shall enable the recording of events relevant for monitoring the operation of high-risk AI systems.
  - VerificationResultVerifier → hasObligation some HighRiskAISystemLoggingCapability
    Rationale: The logging capabilities shall provide the identification of the natural persons involved in the verification of the results.
  - DeployersInterpretability → hasObligation some TransparencyObligation
    Rationale: High-risk AI systems shall be designed and developed to ensure their operation is sufficiently transparent to enable deployers to interpret a system’s output and use it appropriately.
  - SystemOutputInterpretability → hasTechnicalMeasure some HighRiskAISystemTransparency
    Rationale: An appropriate type and degree of transparency shall be ensured with a view to achieving compliance with the relevant obligations of the provider and deployer.
  - AppropriateTransparency → hasLegalBasis some ProviderObligations
    Rationale: An appropriate type and degree of transparency shall be ensured with a view to achieving compliance with the relevant obligations of the provider and deployer set out in Section 3.
  - HighRiskAISystemDocumentation → hasObligation some TransparencyObligation
    Rationale: High-risk AI systems shall be accompanied by instructions for use that include concise, complete, correct and clear information that is relevant, accessible and comprehensible to deployers.
  - HighRiskAISystemDocumentation → hasNotice some HighRiskAISystemTransparency
    Rationale: High-risk AI systems shall be accompanied by instructions for use that include concise, complete, correct and clear information that is relevant, accessible and comprehensible to deployers.
  - AuthorisedRepresentative → hasLegalBasis some TransparencyObligation
    Rationale: The instructions for use shall contain the identity and contact details of the provider and, where applicable, of its authorised representative.
  - HighRiskAISystemPerformance → hasTechnicalMeasure some TransparencyObligation
    Rationale: The instructions for use shall contain information on the characteristics, capabilities and limitations of performance of the high-risk AI system.
  - SystemLimitation → hasTechnicalMeasure some HighRiskAISystemTransparency
    Rationale: The instructions for use shall contain information on the limitations of performance of the high-risk AI system.
  - HighRiskAISystemCybersecurity → hasRisk some RiskAssessment
    Rationale: The text mentions 'the level of accuracy, including its metrics, robustness and cybersecurity' which implies a risk assessment for high-risk AI system cybersecurity.
  - HighRiskAISystemCybersecurity → hasTechnicalMeasure some DataSecurityManagement
    Rationale: The text refers to 'cybersecurity' which is related to technical measures for data security management.
  - HighRiskAISystemCybersecurity → hasNotice some TransparencyObligation
    Rationale: The text states that 'The instructions for use shall contain at least the following information' which implies a transparency obligation.
  - HighRiskAISystemTransparency → hasTechnicalMeasure some HighRiskAISystemLoggingCapability
    Rationale: The instructions for use shall contain information on the technical capabilities and characteristics of the high-risk AI system to provide information relevant to explain its output.
  - HighRiskAISystemTransparency → hasTechnicalMeasure some AutomaticallyGeneratedLogs
    Rationale: The instructions for use shall contain information on the technical capabilities and characteristics of the high-risk AI system to provide information relevant to explain its output.
  - AIOutputExplanation → hasTechnicalMeasure some HighRiskAISystemLoggingCapability
    Rationale: The instructions for use shall contain information on the technical capabilities and characteristics of the high-risk AI system to provide information relevant to explain its output.
  - HighRiskAISystemTrainingData → hasPurpose some HighRiskAISystem
    Rationale: The instructions for use shall contain specifications for the input data, or any other relevant information in terms of the training, validation and testing data sets used, taking into account the intended purpose of the high-risk AI system.
  - HighRiskAISystemTrainingData → hasTechnicalMeasure some DataSecurityManagement
    Rationale: The instructions for use shall contain specifications for the input data, or any other relevant information in terms of the training, validation and testing data sets used.
  - HighRiskAISystemTrainingData → hasNotice some TransparencyObligation
    Rationale: The instructions for use shall contain at least the following information: (vi) when appropriate, specifications for the input data, or any other relevant information in terms of the training, validation and testing data sets used, taking into account the intended purpose of the high-risk AI system.
  - PredeterminedSystemChanges → hasTechnicalMeasure some HighRiskAISystem
    Rationale: The instructions for use shall contain information on the changes to the high-risk AI system and its performance pre-determined by the provider.
  - SystemPerformanceChange → hasTechnicalMeasure some HighRiskAISystem
    Rationale: The instructions for use shall contain information on the changes to the high-risk AI system and its performance pre-determined by the provider.
  - MaintenanceAndCareMeasures → hasTechnicalMeasure some HighRiskAISystem
    Rationale: The instructions for use shall contain ... the expected lifetime of the high-risk AI system and any necessary maintenance and care measures, including their frequency, to ensure the proper functioning of that AI system, including as regards software updates;
  - HighRiskAILogMechanism → hasTechnicalMeasure some HighRiskAISystemLoggingCapability
    Rationale: The instructions for use shall contain a description of the mechanisms included within the high-risk AI system that allows deployers to properly collect, store and interpret the logs.
  - LogCollectionMechanism → hasTechnicalMeasure some AutomaticallyGeneratedLogs
    Rationale: The instructions for use shall contain a description of the mechanisms included within the high-risk AI system that allows deployers to properly collect, store and interpret the logs.
  - LogStorageMechanism → hasTechnicalMeasure some HighRiskAISystemLogRetention
    Rationale: The instructions for use shall contain a description of the mechanisms included within the high-risk AI system that allows deployers to properly collect, store and interpret the logs.
  - LogInterpretationMechanism → hasTechnicalMeasure some HighRiskAISystemTransparency
    Rationale: The instructions for use shall contain a description of the mechanisms included within the high-risk AI system that allows deployers to properly collect, store and interpret the logs.
  - HumanMachineInterface → hasObligation some HumanOversight
    Rationale: High-risk AI systems shall be designed and developed in such a way, including with appropriate human-machine interface tools, that they can be effectively overseen by natural persons during the period in which they are in use.
  - HighRiskAISystemAutonomyLevel → hasRisk some RiskAssessment
    Rationale: The oversight measures shall be commensurate with the risks, level of autonomy and context of use of the high-risk AI system.
  - HighRiskAISystemAutonomyLevel → hasTechnicalOrganisationalMeasure some HumanOversight
    Rationale: The oversight measures shall be ensured through either one or both of the following types of measures: (b) measures identified by the provider before placing the high-risk AI system on the market or putting it into service and that are appropriate to be implemented by the deployer.
  - LimitationUnderstanding → hasPurpose some HumanOversight
    Rationale: The text states that natural persons assigned to human oversight must be enabled to properly understand the relevant capacities and limitations of the high-risk AI system.
  - DysfunctionMonitoring → hasPurpose some HumanOversight
    Rationale: The text states that natural persons assigned to human oversight must be enabled to duly monitor the operation of the high-risk AI system, including detecting and addressing anomalies and dysfunctions.
  - HighRiskAISystem → hasRisk some HumanOversight
    Rationale: The text mentions 'human oversight' assigned to natural persons for high-risk AI systems.
  - HighRiskAISystem → hasRisk some AutomationBias
    Rationale: The text mentions 'automation bias' as a possible tendency of automatically relying or over-relying on the output produced by a high-risk AI system.
  - HighRiskAISystem → hasTechnicalOrganisationalMeasure some HumanInvolvementForOversight
    Rationale: The text mentions 'human oversight' and natural persons to whom human oversight is assigned.
  - InterpretationTool → hasPurpose some HumanOversight
    Rationale: The text mentions that natural persons to whom human oversight is assigned are enabled to correctly interpret the high-risk AI system's output.
  - HighRiskAISystemOverride → hasLegalBasis some HumanOversight
    Rationale: Article 14(4) specifies that natural persons assigned human oversight can decide not to use the high-risk AI system or override its output.
  - HighRiskAISystemOverride → hasPurpose some HumanOversightDecision
    Rationale: The high-risk AI system must allow for human oversight to decide in any particular situation.
  - StopButton → hasPurpose some HumanOversight
    Rationale: The text states that the 'stop' button allows natural persons to intervene in the operation of the high-risk AI system for the purpose of human oversight.
  - SafeStateHalt → hasTechnicalMeasure some HighRiskAISystem
    Rationale: The text mentions that the system should come to a halt in a safe state through a 'stop' button or a similar procedure.
  - Accuracy → hasTechnicalMeasure some AccuracyDegree
    Rationale: High-risk AI systems shall be designed and developed in such a way that they achieve an appropriate level of accuracy.
  - Robustness → hasTechnicalMeasure some RobustnessMetric
    Rationale: High-risk AI systems shall be designed and developed in such a way that they achieve an appropriate level of robustness.
  - MeasurementMethodology → hasLegalBasis some UnionLawException
    Rationale: The Commission shall encourage development of benchmarks and measurement methodologies as per Article 15(2) under the EU AI Act.
  - MeasurementMethodology → hasTechnicalMeasure some RobustnessMetric
    Rationale: The development of benchmarks and measurement methodologies addresses technical aspects of accuracy and robustness.
  - MeasurementMethodology → hasPurpose some AccuracyDegree
    Rationale: Measurement methodologies aim to measure appropriate levels of accuracy and robustness.
  - AccuracyMetric → hasTechnicalMeasure some HighRiskAISystem
    Rationale: The levels of accuracy and the relevant accuracy metrics of high-risk AI systems shall be declared in the accompanying instructions of use.
  - FeedbackLoop → isMitigatedByMeasure some RiskManagementMeasure
    Rationale: High-risk AI systems that continue to learn after being placed on the market or put into service shall be developed in such a way as to eliminate or reduce as far as possible the risk of possibly biased outputs influencing input for future operations (feedback loops), and as to ensure that any such feedback loops are duly addressed with appropriate mitigation measures.
  - FeedbackLoop → hasRisk some BiasDetectionCorrection
    Rationale: High-risk AI systems that continue to learn after being placed on the market or put into service shall be developed in such a way as to eliminate or reduce as far as possible the risk of possibly biased outputs influencing input for future operations (feedback loops)
  - AIResilience → hasTechnicalMeasure some DataSecurityManagement
    Rationale: The technical solutions aiming to ensure the cybersecurity of high-risk AI systems shall be appropriate to the relevant circumstances and the risks.
  - CybersecurityOfHighRiskAI → hasTechnicalOrganisationalMeasure some RiskManagementSystem
    Rationale: The technical solutions aiming to ensure the cybersecurity of high-risk AI systems shall be appropriate to the relevant circumstances and the risks.
  - DataPoisoning → isMitigatedByMeasure some RiskMitigationSafeguard
    Rationale: The technical solutions to address AI specific vulnerabilities shall include, where appropriate, measures to prevent, detect, respond to, resolve and control for attacks trying to manipulate the training data set (data poisoning).
  - ModelPoisoning → isMitigatedByMeasure some RiskMitigationSafeguard
    Rationale: The technical solutions to address AI specific vulnerabilities shall include, where appropriate, measures to prevent, detect, respond to, resolve and control for attacks trying to manipulate the pre-trained components used in training (model poisoning).
  - AdversarialExamples → isMitigatedByMeasure some RiskMitigationSafeguard
    Rationale: The technical solutions to address AI specific vulnerabilities shall include, where appropriate, measures to prevent, detect, respond to, resolve and control for inputs designed to cause the AI model to make a mistake (adversarial examples or model evasion).
  - ConfidentialityAttack → isMitigatedByMeasure some DataSecurityManagement
    Rationale: The technical solutions to address AI specific vulnerabilities shall include, where appropriate, measures to prevent, detect, respond to, resolve and control for confidentiality attacks.
  - ProviderObligations → hasObligation some HighRiskAISystem
    Rationale: Providers of high-risk AI systems shall ensure that their high-risk AI systems are compliant with the requirements.
  - ProviderObligations → hasLegalBasis some UnionLawException
    Rationale: The obligations are set out in Article 16(1) of the EU AI Act.
  - HighRiskAiSystemPackaging → hasObligation some TransparencyObligation
    Rationale: Providers of high-risk AI systems shall indicate on the high-risk AI system or, where that is not possible, on its packaging or its accompanying documentation.
  - HighRiskAISystemLogRetention → hasObligation some HighRiskAISystemLoggingCapability
    Rationale: Providers of high-risk AI systems shall keep the logs automatically generated by their high-risk AI systems.
  - HighRiskAIIncidentLog → hasObligation some AutomaticallyGeneratedLogs
    Rationale: Providers of high-risk AI systems shall keep the logs automatically generated by their high-risk AI systems as referred to in Article 19.
  - HighRiskAIConformityAssessment → hasLegalBasis some ConformityAssessmentProcedure
    Rationale: The regulatory text mentions 'the relevant conformity assessment procedure as referred to in Article 43'.
  - HighRiskAISystemProviderObligations → hasObligation some ConformityAssessmentProcedure
    Rationale: Providers of high-risk AI systems shall ensure that the high-risk AI system undergoes the relevant conformity assessment procedure.
  - HighRiskAISystemProvider → hasObligation some ConformityDeclaration
    Rationale: Providers of high-risk AI systems shall draw up an EU declaration of conformity in accordance with Article 47.
  - CEMarking → hasLegalBasis some ConformityDeclaration
    Rationale: Providers of high-risk AI systems shall affix the CE marking to indicate conformity with this Regulation, in accordance with Article 48.
  - PackagingDocumentation → hasLegalBasis some ConformityDeclaration
    Rationale: Providers of high-risk AI systems shall affix the CE marking to the high-risk AI system or, where that is not possible, on its packaging or its accompanying documentation, to indicate conformity with this Regulation, in accordance with Article 48.
  - HighRiskAISystemAccessibility → hasLegalBasis some AccessibilityRequirement
    Rationale: Providers of high-risk AI systems shall ensure that the high-risk AI system complies with accessibility requirements in accordance with Directives (EU) 2016/2102 and (EU) 2019/882.
  - ModificationManagementProcedure → hasLegalBasis some ConformityAssessmentProcedure
    Rationale: that system shall include at least the following aspects: (a) a strategy for regulatory compliance, including compliance with conformity assessment procedures
  - QualityControlProcedure → hasTechnicalMeasure some RiskManagementSystem
    Rationale: Techniques, procedures and systematic actions for development, quality control and quality assurance of high-risk AI systems.
  - QualityAssuranceAction → hasTechnicalMeasure some RiskManagementSystem
    Rationale: Techniques, procedures and systematic actions for development, quality control and quality assurance of high-risk AI systems.
  - QualityControlProcedure → hasObligation some ComplianceDemonstration
    Rationale: Providers of high-risk AI systems shall put a quality management system in place that ensures compliance with this Regulation.
  - QualityAssuranceAction → hasObligation some ComplianceDemonstration
    Rationale: Providers of high-risk AI systems shall put a quality management system in place that ensures compliance with this Regulation.
  - ExaminationProcedure → hasTechnicalMeasure some QualityManagementSystem
    Rationale: Providers of high-risk AI systems shall put a quality management system in place that ensures compliance with this Regulation, and includes examination procedures.
  - TestProcedure → hasTechnicalMeasure some QualityManagementSystem
    Rationale: Providers of high-risk AI systems shall put a quality management system in place that ensures compliance with this Regulation, and includes test procedures.
  - ValidationProcedure → hasTechnicalMeasure some QualityManagementSystem
    Rationale: Providers of high-risk AI systems shall put a quality management system in place that ensures compliance with this Regulation, and includes validation procedures.
  - QualityManagementSystem → hasTechnicalMeasure some TechnicalSpecification
    Rationale: Providers of high-risk AI systems shall put a quality management system in place that ensures compliance with this Regulation, including technical specifications.
  - TechnicalSpecification → hasLegalBasis some HarmonisedStandards
    Rationale: The quality management system shall include technical specifications, including standards, to be applied and, where the relevant harmonised standards are not applied in full.
  - ComplianceMeans → hasTechnicalOrganisationalMeasure some TechnicalSpecification
    Rationale: The quality management system shall include at least the following aspects: (e) technical specifications, including standards, to be applied.
  - WrittenPolicies → hasLegalBasis some QualityManagementSystem
    Rationale: Providers of high-risk AI systems shall put a quality management system in place that ensures compliance with this Regulation.
  - QualityManagementSystemDocumentation → hasObligation some PostMarketSurveillance
    Rationale: that system shall include at least the following aspects: (h) the setting-up, implementation and maintenance of a post-market monitoring system, in accordance with Article 72;
  - ResourceManagement → hasTechnicalOrganisationalMeasure some QualityManagementSystem
    Rationale: Providers of high-risk AI systems shall put a quality management system in place that ensures compliance with this Regulation, including resource management.
  - SecurityOfSupply → hasTechnicalOrganisationalMeasure some QualityManagementSystem
    Rationale: Providers of high-risk AI systems shall put a quality management system in place that ensures compliance with this Regulation, including security-of-supply related measures.
  - AccountabilityFramework → hasTechnicalOrganisationalMeasure some QualityManagementSystem
    Rationale: The regulatory text states that the quality management system shall include an accountability framework setting out responsibilities.
  - FinancialInstitutionInternalGovernance → hasObligation some QualityManagementSystem
    Rationale: The text states that providers that are financial institutions subject to requirements regarding their internal governance shall be deemed to have fulfilled the obligation to put in place a quality management system by complying with the rules on internal governance arrangements or processes pursuant to the relevant Union financial services law.
  - NationalCompetentAuthoritiesDocumentationAccess → hasObligation some HighRiskAISystemDocumentationRetention
    Rationale: The provider shall keep at the disposal of the national competent authorities.
  - DocumentationRetentionPeriod → hasObligation some HighRiskAISystemLogRetention
    Rationale: The provider shall keep at the disposal of the national competent authorities the documentation for a period ending 10 years after the high-risk AI system has been placed on the market or put into service.
  - NotifiedBodyDecision → hasLegalBasis some HighRiskAISystem
    Rationale: The provider shall keep decisions and documents issued by notified bodies at the disposal of national competent authorities for 10 years after the high-risk AI system has been placed on the market or put into service.
  - DocumentationKeepingPeriod → hasLegalBasis some EUDeclarationOfConformity
    Rationale: The provider shall keep at the disposal of the national competent authorities the EU declaration of conformity referred to in Article 47.
  - DocumentationRetentionCondition → hasLegalBasis some UnionLawException
    Rationale: The text mentions 'conditions under which the documentation... remains at the disposal of the national competent authorities' implying a legal basis related to Union law exceptions.
  - ProviderInsolvency → hasObligation some AuthorisedRepresentative
    Rationale: The text mentions 'a provider or its authorised representative established on its territory goes bankrupt or ceases its activity' indicating an obligation related to authorised representatives.
  - HighRiskAILog → hasLegalBasis some UnionLawException
    Rationale: The text mentions 'Without prejudice to applicable Union or national law'.
  - LogControl → hasTechnicalOrganisationalMeasure some DataSecurityManagement
    Rationale: The text implies logs are under the control of providers and must be kept appropriately.
  - LogRetentionPeriod → hasPurpose some HighRiskAISystemLogRetention
    Rationale: The text states logs shall be kept for a period appropriate to the intended purpose of the high-risk AI system.
  - AutomaticallyGeneratedLogs → hasObligation some HighRiskAISystemLogRetention
    Rationale: The text states 'maintain the logs automatically generated by their high-risk AI systems'.
  - SystemWithdrawal → hasLegalBasis some RegulationAmendmentRestriction
    Rationale: Providers shall withdraw the high-risk AI system if it is not in conformity with this Regulation.
  - SystemDisabling → hasLegalBasis some RegulationAmendmentRestriction
    Rationale: Providers shall disable the high-risk AI system if it is not in conformity with this Regulation.
  - SystemRecall → hasLegalBasis some RegulationAmendmentRestriction
    Rationale: Providers shall recall the high-risk AI system if it is not in conformity with this Regulation.
  - MarketSurveillanceAuthority → hasObligation some HighRiskAISystem
    Rationale: The regulatory text mentions that the market surveillance authorities are informed about the non-compliance and corrective actions taken for high-risk AI systems.
  - MarketSurveillanceAuthority → hasLegalBasis some UnionLawException
    Rationale: The regulatory text refers to Article 79(1) and Article 44, implying a legal basis in Union law for market surveillance authorities' actions.
  - HighRiskAIConformityDocumentation → hasLegalBasis some ReasonedRequest
    Rationale: Providers of high-risk AI systems shall, upon a reasoned request by a competent authority, provide that authority all the information and documentation necessary to demonstrate the conformity of the high-risk AI system with the requirements set out in Section 2.
  - CompetentAuthorityRequest → hasRight some ReasonedRequest
    Rationale: The text mentions 'upon a reasoned request by a competent authority'.
  - DeployersObligations → hasObligation some HumanOversight
    Rationale: Deployers shall assign human oversight to natural persons.
  - HighRiskAISystemDeployer → hasObligation some HumanOversight
    Rationale: Deployers shall assign human oversight to natural persons.
  - DeployerControlOverInputData → hasObligation some InputDataRelevance
    Rationale: The deployer shall ensure that input data is relevant.
  - DeployerControlOverInputData → hasObligation some InputDataRepresentativeness
    Rationale: The deployer shall ensure that input data is sufficiently representative.
  - HighRiskAISystemInputData → hasRisk some RiskAssessment
    Rationale: The input data is used in a high-risk AI system.
  - FinancialInstitutionsLogRequirement → hasObligation some HighRiskAISystemLogRetention
    Rationale: Deployers of high-risk AI systems shall keep the logs automatically generated by that high-risk AI system to the extent such logs are under their control, for a period appropriate to the intended purpose of the high-risk AI system, of at least six months.
  - HighRiskAISystemWorkplaceDeployment → hasObligation some TransparencyObligation
    Rationale: Deployers who are employers shall inform workers’ representatives and the affected workers that they will be subject to the use of the high-risk AI system.
  - HighRiskAISystemWorkplaceDeployment → hasLegalBasis some UnionLawException
    Rationale: This information shall be provided, where applicable, in accordance with the rules and procedures laid down in Union and national law and practice on information of workers and their representatives.
  - PublicAuthorityDeployer → hasObligation some EUdatabaseRegistrationObligation
    Rationale: Deployers of high-risk AI systems that are public authorities shall comply with the registration obligations referred to in Article 49.
  - UnionInstitutionDeployer → hasObligation some EUdatabaseRegistrationObligation
    Rationale: Deployers of high-risk AI systems that are Union institutions, bodies, offices or agencies shall comply with the registration obligations referred to in Article 49.
  - PublicAuthorityDeployer → hasLegalBasis some EUdatabaseRegistrationObligation
    Rationale: Deployers of high-risk AI systems that are public authorities shall not use a system that has not been registered in the EU database referred to in Article 71.
  - UnionInstitutionDeployer → hasLegalBasis some EUdatabaseRegistrationObligation
    Rationale: Deployers of high-risk AI systems that are Union institutions, bodies, offices or agencies shall not use a system that has not been registered in the EU database referred to in Article 71.
  - PostRemoteBiometricIdentification → hasLegalBasis some UnionLawException
    Rationale: The use of post-remote biometric identification systems must be in accordance with Union law.
  - PostRemoteBiometricIdentification → hasPurpose some LawEnforcementProfiling
    Rationale: The system is used for the targeted search of a person suspected or convicted of having committed a criminal offence.
  - PostRemoteBiometricIdentification → hasObligation some TransparencyObligation
    Rationale: Each use of such high-risk AI systems shall be documented in the relevant police file and shall be made available to the relevant market surveillance authority and the national data protection authority upon request.
  - AdverseLegalEffect → hasRisk some RiskAssessment
    Rationale: No decision that produces an adverse legal effect on a person may be taken by the law enforcement authorities based solely on the output of such post-remote biometric identification systems.
  - HighRiskAISystemDeployment → hasObligation some TransparencyObligation
    Rationale: Deployers of high-risk AI systems shall inform natural persons that they are subject to the use of the high-risk AI system.
  - LawEnforcementHighRiskAISystem → hasLegalBasis some AnnexIII
    Rationale: High-risk AI systems used for law enforcement purposes are referred to in Annex III.
  - CooperationWithAuthority → hasObligation some HighRiskAISystem
    Rationale: Deployers shall cooperate with the relevant competent authorities in any action those authorities take in relation to the high-risk AI system.
  - NotificationApplication → hasLegalBasis some UnionLawException
    Rationale: The application for notification shall be accompanied by documents related to existing designations under any other Union harmonisation legislation.
  - NotificationApplication → hasLegalBasis some DesignationUnderUnionLegislation
    Rationale: Any valid document related to existing designations of the applicant notified body under any other Union harmonisation legislation shall be added.
  - NotificationApplication → hasObligation some ConformityAssessmentProcedure
    Rationale: The application for notification shall be accompanied by a description of the conformity assessment activities, the conformity assessment module or modules and the types of AI systems for which the conformity assessment body claims to be competent.
  - NotificationApplication → hasTechnicalOrganisationalMeasure some RiskManagementSystem
    Rationale: The application for notification shall be accompanied by a description of the conformity assessment activities, the conformity assessment module or modules and the types of AI systems for which the conformity assessment body claims to be competent.
  - LawfulAIExceptions → hasLegalBasis some UnionLawException
    Rationale: The text mentions 'AI systems authorised by law to detect, prevent, investigate or prosecute criminal offences'.
  - PublicCriminalOffenceReporting → hasObligation some TransparencyObligation
    Rationale: The text states that the obligation does not apply to AI systems for reporting a criminal offence.
  - ArtificialContentDetection → hasObligation some TransparencyObligation
    Rationale: Providers of AI systems generating synthetic content shall ensure outputs are marked in a machine-readable format and detectable as artificially generated or manipulated.
  - ArtificialContentDetection → hasTechnicalMeasure some HighRiskAISystemTransparency
    Rationale: Providers shall ensure their technical solutions are effective, interoperable, robust and reliable as far as this is technically feasible.
  - ArtisticCreativeWork → hasObligation some TransparencyObligation
    Rationale: Deployers of an AI system that generates or manipulates image, audio or video content constituting a deep fake, shall disclose that the content has been artificially generated or manipulated, and where the content forms part of an evidently artistic, creative, satirical, fictional or analogous work or programme, the transparency obligations set out in this paragraph are limited to disclosure of the existence of such generated or manipulated content.
  - ClearAndDistinguishableInformation → hasObligation some TransparencyObligation
    Rationale: The information shall be provided in a clear and distinguishable manner at the latest at the time of the first interaction or exposure.
  - FirstInteractionExposure → hasTechnicalMeasure some HighRiskAISystemTransparency
    Rationale: The information referred to in paragraphs 1 to 4 shall be provided to the natural persons concerned at the latest at the time of the first interaction or exposure.
  - AccessibilityRequirements → hasLegalBasis some AccessibilityRequirement
    Rationale: The information shall conform to the applicable accessibility requirements.
  - CodeOfPractice → hasLegalBasis some UnionLawException
    Rationale: The Commission may adopt implementing acts to approve those codes of practice in accordance with the procedure laid down in Article 56 (6).
  - TransparencyObligationImplementation → hasObligation some TransparencyObligation
    Rationale: The AI Office shall encourage and facilitate the drawing up of codes of practice at Union level to facilitate the effective implementation of the obligations regarding the detection and labelling of artificially generated or manipulated content.
  - SystemicRisk → hasRiskAssessment some RiskAssessment
    Rationale: A general-purpose AI model shall be classified as a general-purpose AI model with systemic risk if it meets any of the following conditions: (a) it has high impact capabilities evaluated on the basis of appropriate technical tools and methodologies, including indicators and benchmarks;
  - CommissionDecisionExOfficio → hasLegalBasis some AnnexXiiiCriteria
    Rationale: The Commission's decision ex officio is based on criteria set out in Annex XIII.
  - ScientificPanelQualifiedAlert → hasLegalBasis some AnnexXiiiCriteria
    Rationale: A qualified alert from the scientific panel is based on criteria set out in Annex XIII.
  - HighImpactCapability → hasLegalBasis some SystemicRisk
    Rationale: A general-purpose AI model shall be presumed to have high impact capabilities pursuant to paragraph 1, point (a) when the cumulative amount of computation used for its training measured in floating point operations is greater than
  - ThresholdAmendment → hasLegalBasis some DelegatedActs
    Rationale: The Commission shall adopt delegated acts in accordance with Article 97 to amend the thresholds.
  - ExceptionalCase → hasLegalBasis some UnionLawException
    Rationale: The text mentions 'exceptionally' and 'should not be classified' implying a legal basis for exceptions under Union law.
  - GeneralPurposeAIModelWithSystemicRisk → hasRisk some SystemicRisk
    Rationale: The text states that the general-purpose AI model shall be considered to be a general-purpose AI model with systemic risk.
  - ReasonedRequest → hasLegalBasis some AnnexIII
    Rationale: The request shall contain objective, detailed and new reasons that have arisen since the designation decision, based on the criteria set out in Annex XIII.
  - TradeSecretProtection → hasLegalBasis some UnionLawException
    Rationale: The text mentions 'in accordance with Union and national law' as the legal basis for protecting trade secrets.
  - AiModelLimitation → hasObligation some ProviderObligations
    Rationale: Providers of general-purpose AI models shall enable providers of AI systems to have a good understanding of the capabilities and limitations of the general-purpose AI model and to comply with their obligations pursuant to this Regulation.
  - ReservationOfRights → hasLegalBasis some UnionLawException
    Rationale: Article 4(3) of Directive (EU) 2019/790 implies a legal basis for reservation of rights.
  - GeneralPurposeAiModelTrainingDataSummary → hasTechnicalMeasure some TransparencyObligation
    Rationale: Providers of general-purpose AI models shall draw up and make publicly available a sufficiently detailed summary about the content used for training.
  - AlternativeMeansOfCompliance → hasLegalBasis some UnionLawException
    Rationale: Providers of general-purpose AI models who do not adhere to an approved code of practice or do not comply with a European harmonised standard shall demonstrate alternative adequate means of compliance for assessment by the Commission.
  - VerifiableDocumentation → hasLegalBasis some DelegatedActs
    Rationale: The Commission is empowered to adopt delegated acts in accordance with Article 97.
  - RemoteBiometricIdentificationSystem → hasLegalBasis some UnionLawException
    Rationale: The use of remote biometric identification systems is permitted under relevant Union or national law.
  - RemoteBiometricIdentificationSystem → hasPurpose some LawEnforcementProfiling
    Rationale: Remote biometric identification systems are used for identification purposes.
  - SensitiveAttributeInference → hasLegalBasis some UnionLawException
    Rationale: The use of biometrics for sensitive attribute inference is subject to relevant Union or national law.
  - ProtectedAttribute → hasLegalBasis some UnionLawException
    Rationale: The use of biometrics for protected attribute identification is subject to relevant Union or national law.
  - CriticalInfrastructure → hasLegalBasis some AnnexIII
    Rationale: AI systems intended to be used as safety components in the management and operation of critical digital infrastructure, road traffic, or in the supply of water, gas, heating or electricity have a legal basis in Annex III.
  - CriticalDigitalInfrastructure → hasLegalBasis some AnnexIII
    Rationale: Critical digital infrastructure is mentioned as part of critical infrastructure in Annex III.
  - RoadTrafficManagement → hasLegalBasis some AnnexIII
    Rationale: Road traffic management is mentioned as part of critical infrastructure in Annex III.
  - UtilitySupply → hasLegalBasis some AnnexIII
    Rationale: Utility supply is mentioned as part of critical infrastructure in Annex III.
  - AIforEducation → hasPurpose some EducationInstitutionAssignment
    Rationale: AI systems intended to be used to determine access or admission or to assign natural persons to educational and vocational training institutions at all levels.
  - EducationInstitutionAssignment → hasLegalBasis some AnnexIII
    Rationale: as per EU AI Act, Annex III, Point 3(a) which specifically mentions education and vocational training institutions.
  - LearningOutcomeEvaluation → hasPurpose some HighRiskAISystem
    Rationale: AI systems intended to be used to evaluate learning outcomes.
  - EducationalInstitution → hasPurpose some HighRiskAISystem
    Rationale: AI systems intended to be used for the purpose of assessing the appropriate level of education
  - StudentMonitoring → hasPurpose some ProhibitedBehaviourDetection
    Rationale: AI systems intended to be used for monitoring and detecting prohibited behaviour of students during tests.
  - ProhibitedBehaviourDetection → hasPurpose some StudentMonitoring
    Rationale: AI systems intended to be used for monitoring and detecting prohibited behaviour of students during tests.
  - CandidateEvaluation → hasPurpose some HighRiskAISystem
    Rationale: AI systems intended to be used for the recruitment or selection of natural persons, in particular to place targeted job advertisements, to analyse and filter job applications, and to evaluate candidates.
  - CandidateEvaluation → hasLegalBasis some UnionLawException
    Rationale: Employment, workers’ management and access to self-employment regulation implies a legal basis for processing personal data.
  - WorkersManagement → hasRisk some RiskAssessment
    Rationale: Employment, workers’ management and access to self-employment implies risks associated with AI systems used in these areas.
  - WorkRelatedRelationships → hasRisk some HighRiskAISystem
    Rationale: AI systems intended to be used to make decisions affecting terms of work-related relationships.
  - TaskAllocation → hasPurpose some WorkRelatedRelationships
    Rationale: allocate tasks based on individual behaviour or personal traits or characteristics.
  - WorkTermDecisions → hasLegalBasis some AnnexIII
    Rationale: AI systems intended to be used to make decisions affecting terms of work-related relationships, the promotion or termination of work-related contractual relationships.
  - EligibilityEvaluation → hasLegalBasis some AnnexIII
    Rationale: The text is part of Annex III, Point 5(a) of the EU AI Act.
  - EssentialPrivateServices → hasRisk some HighRiskAISystem
    Rationale: AI systems intended to be used to evaluate the creditworthiness of natural persons or establish their credit score.
  - LifeAndHealthInsuranceRiskAssessment → hasRiskAssessment some RiskAssessment
    Rationale: AI systems intended to be used for risk assessment and pricing in relation to natural persons in the case of life and health insurance.
  - LifeAndHealthInsuranceRiskAssessment → hasPurpose some EssentialPrivateServices
    Rationale: Access to and enjoyment of essential private services
  - EmergencyCallEvaluation → hasPurpose some EmergencyFirstResponseService
    Rationale: AI systems intended to evaluate and classify emergency calls by natural persons or to be used to dispatch, or to establish priority in the dispatching of, emergency first response services.
  - EmergencyFirstResponseService → hasPurpose some EssentialPrivateService
    Rationale: Access to and enjoyment of essential private services and essential public services and benefits.
  - VictimRiskAssessment → hasRiskAssessment some RiskAssessment
    Rationale: The text mentions AI systems intended to assess the risk of a natural person becoming the victim of criminal offences.
  - LawEnforcementAI → hasPurpose some LawEnforcementProfiling
    Rationale: The text mentions AI systems used by or on behalf of law enforcement authorities.
  - CriminalOffenceVictim → hasRisk some RiskAssessment
    Rationale: The text mentions assessing the risk of a natural person becoming the victim of criminal offences.
  - LawEnforcementEvidenceEvaluation → hasLegalBasis some UnionLawException
    Rationale: The text mentions 'in so far as their use is permitted under relevant Union or national law'.
  - LawEnforcementProfiling → hasLegalBasis some UnionLawException
    Rationale: The text mentions 'in so far as their use is permitted under relevant Union or national law'.
  - LawEnforcementProfiling → hasPurpose some CriminalOffenceInvestigation
    Rationale: The text mentions 'in support of law enforcement authorities for the profiling ... in the course of the detection, investigation or prosecution of criminal offences'.
  - NaturalPersonProfiling → hasPurpose some CriminalOffenceInvestigation
    Rationale: The text mentions 'for the profiling of natural persons ... in the course of the detection, investigation or prosecution of criminal offences'.
  - AISystemforPolygraph → hasLegalBasis some UnionLawException
    Rationale: The text mentions 'in so far as their use is permitted under relevant Union or national law'.
  - AISystemforPolygraph → hasPurpose some HighRiskAISystem
    Rationale: The text describes AI systems intended to be used as polygraphs or similar tools.
  - AISystemforPolygraph → hasObligation some TransparencyObligation
    Rationale: The use by public authorities or Union institutions implies obligations.
  - HealthRiskAssessment → hasRiskAssessment some RiskAssessment
    Rationale: The text mentions 'a health risk, posed by a natural person who intends to enter or who has entered into the territory of a Member State'.
  - IrregularMigrationRiskAssessment → hasRiskAssessment some RiskAssessment
    Rationale: The text mentions 'a risk of irregular migration, posed by a natural person who intends to enter or who has entered into the territory of a Member State'.
  - AsylumRiskAssessment → hasRiskAssessment some RiskAssessment
    Rationale: The text mentions 'assess a risk, including a security risk, a risk of irregular migration, or a health risk, posed by a natural person who intends to enter or who has entered into the territory of a Member State'.
  - BorderControlManagement → hasRiskAssessment some RiskAssessment
    Rationale: The text mentions 'migration, asylum and border control management' and 'assess a risk'.
  - TravelDocumentVerificationExemption → hasLegalBasis some UnionLawException
    Rationale: The text mentions 'with the exception of the verification of travel documents' implying a legal basis in Union law for this exemption.
  - SoftwareVersion → hasTechnicalMeasure some VersionUpdateRequirement
    Rationale: The text mentions 'the versions of relevant software or firmware, and any requirements related to version updates'.
  - FirmwareVersion → hasTechnicalMeasure some VersionUpdateRequirement
    Rationale: The text mentions 'the versions of relevant software or firmware, and any requirements related to version updates'.
  - SoftwarePackage → hasTechnicalMeasure some DataSecurityManagement
    Rationale: The description of AI systems includes software packages, implying a need for data security management as a technical measure.
  - SoftwarePackage → hasRiskAssessment some RiskAssessment
    Rationale: The general description of AI systems, including software packages, requires a risk assessment.
  - Marking → hasTechnicalMeasure some CEMarking
    Rationale: The text mentions 'marking' and 'CEMarking' is a relevant technical measure.
  - ThirdPartySystemIntegration → hasTechnicalMeasure some ModificationManagementProcedure
    Rationale: The text mentions 'recourse to pre-trained systems or tools provided by third parties and how those were used, integrated or modified by the provider'.
  - ThirdPartySystemIntegration → hasTechnicalMeasure some DataSecurityManagement
    Rationale: The text implies the need for secure integration of third-party systems.
  - TechnicalSolutionTradeOff → hasPurpose some RiskManagementMeasure
    Rationale: The text mentions 'decisions about any possible trade-off made regarding the technical solutions adopted to comply with the requirements set out in Chapter III, Section 2'.
  - TechnicalSolutionTradeOff → hasTechnicalMeasure some RiskMitigationSafeguard
    Rationale: The text mentions 'decisions about any possible trade-off made regarding the technical solutions adopted to comply with the requirements set out in Chapter III, Section 2'.
  - TechnicalSolutionTradeOff → hasRiskAssessment some RiskAssessment
    Rationale: The text mentions 'the main classification choices; what the system is designed to optimise for, and the relevance of the different parameters'.
  - SoftwareComponentIntegration → hasTechnicalMeasure some DataSecurityManagement
    Rationale: The text describes the system architecture explaining how software components integrate into the overall processing.
  - SoftwareComponentIntegration → hasTechnicalMeasure some PrivacyByDesign
    Rationale: The text mentions software components building on or feeding into each other.
  - TrainingDataSet → hasTechnicalMeasure some DataSecurityManagement
    Rationale: The text mentions 'labelling procedures' and 'data cleaning methodologies' which implies technical measures for data security management.
  - TrainingDataSet → hasTechnicalMeasure some PrivacyByDesign
    Rationale: The text mentions 'data requirements in terms of datasheets describing the training methodologies and techniques' which implies technical measures for privacy by design.
  - TrainingDataSet → hasRiskAssessment some RiskAssessment
    Rationale: The text mentions 'data requirements' and 'provanance, scope and main characteristics' which implies a risk assessment.
  - ValidationTestingData → hasTechnicalMeasure some DataSecurityManagement
    Rationale: The text mentions 'information about the validation and testing data used and their main characteristics' and 'test logs and all test reports dated and signed by the responsible persons', implying a technical measure for data security management.
  - RobustnessMetric → hasTechnicalMeasure some DataSecurityManagement
    Rationale: The text mentions 'metrics used to measure accuracy, robustness and compliance with other relevant requirements', implying a technical measure for data security management.
  - ValidationTestingData → hasRiskAssessment some RiskAssessment
    Rationale: The text mentions 'potentially discriminatory impacts', implying a risk assessment.
  - RobustnessMetric → hasRiskAssessment some RiskAssessment
    Rationale: The text mentions 'metrics used to measure accuracy, robustness and compliance with other relevant requirements', implying a risk assessment.
  - CybersecurityMeasure → hasTechnicalMeasure some DataSecurityManagement
    Rationale: The regulatory text mentions 'cybersecurity measures' which are a type of technical measure for data security management.
  - AccuracyDegree → hasRisk some RiskToFundamentalRights
    Rationale: The text mentions 'degrees of accuracy for specific persons or groups of persons' and 'risks to ... fundamental rights'.
  - RiskToFundamentalRights → hasRiskAssessment some RiskAssessment
    Rationale: The text mentions 'foreseeable unintended outcomes and sources of risks to ... fundamental rights'.
  - PerformanceMetricAppropriateness → hasRiskAssessment some RiskAssessment
    Rationale: The text mentions 'the appropriateness of the performance metrics for the specific AI system', implying a relation to risk assessment.
  - SystemLifecycleChanges → hasTechnicalOrganisationalMeasure some RiskManagementSystem
    Rationale: A description of relevant changes made by the provider to the system through its lifecycle implies involvement of risk management.
  - SystemLifecycleChanges → hasRiskAssessment some RiskAssessment
    Rationale: Lifecycle changes involve assessments of risks.
  - SolutionAdopted → hasTechnicalMeasure some OtherRelevantStandard
    Rationale: The text mentions 'a list of other relevant standards and technical specifications applied' as part of the solutions adopted to meet the requirements.
  - CustomMadeDevice → hasLegalBasis some RegulationAmendmentRestriction
    Rationale: The regulatory text defines 'custom-made device' in relation to Part II, implying a legal basis in Regulation 5(1).
  - RelevantDevice → hasLegalBasis some RegulationAmendmentRestriction
    Rationale: The term 'relevant device' is defined in relation to Part II and Regulation 6, indicating a legal basis.
  - SystemOrProcedurePack → hasLegalBasis some RegulationAmendmentRestriction
    Rationale: The definition of 'system or procedure pack' references Article 12 of Directive 93/42, implying a legal basis.
  - GeneralMedicalDevice → hasLegalBasis some MedicalDeviceClassification
    Rationale: Devices are classified as belonging to Class I, IIa, IIb or III in accordance with the classification criteria.
  - MedicalDeviceClassification → hasLegalBasis some ClassificationCriteria
    Rationale: Devices are classified as belonging to Class I, IIa, IIb or III in accordance with the classification criteria set out in Annex IX.
  - ClassI → hasLegalBasis some MedicalDeviceClassification
    Rationale: Devices are classified as belonging to Class I, IIa, IIb or III.
  - ClassIIa → hasLegalBasis some MedicalDeviceClassification
    Rationale: Devices are classified as belonging to Class I, IIa, IIb or III.
  - ClassIIb → hasLegalBasis some MedicalDeviceClassification
    Rationale: Devices are classified as belonging to Class I, IIa, IIb or III.
  - ClassIII → hasLegalBasis some MedicalDeviceClassification
    Rationale: Devices are classified as belonging to Class I, IIa, IIb or III.
  - DeviceClassificationDispute → hasLegalBasis some RegulatoryExemption
    Rationale: The classification of a device in dispute is determined in accordance with the classification criteria set out in Annex IX of Directive 93/42.
  - SecretaryOfStateDetermination → hasLegalBasis some UnionLawException
    Rationale: The Secretary of State determines the classification of the device in accordance with Directive 93/42, read with Directive 2003/12 and Directive 2005/50.
  - DeviceSupply → hasLegalBasis some Regulation7222012
    Rationale: The text mentions 'the requirements set out in Regulation (EU) No 722/2012 (if applicable)'.
  - DeviceSupply → hasLegalBasis some GeneralMedicalDevice
    Rationale: The text mentions 'unless that device meets those essential requirements set out in Annex I which apply to it'.
  - MedicalDeviceHazard → hasLegalBasis some GeneralMedicalDevice
    Rationale: Devices which are also machinery shall also meet the essential health and safety requirements set out in Part 1 of Schedule 2 to the Supply of Machinery (Safety) Regulations 2008.
  - RelevantEssentialRequirements → hasPurpose some IntendedPurpose
    Rationale: The regulation states that account shall be taken of the device's intended purpose.
  - AnnexVIIIConditions → hasLegalBasis some RegulationAmendmentRestriction
    Rationale: The conditions specified in Annex VIII are mentioned as a basis for clinical investigation.
  - EssentialRequirementsCompliance → hasLegalBasis some UnionLawException
    Rationale: The device shall be taken to comply with the relevant essential requirements unless there are reasonable grounds for suspecting that the device does not comply with those requirements.
  - ReasonableGroundsforSuspection → hasRisk some RiskAssessment
    Rationale: There are reasonable grounds for suspecting that the device does not comply with those requirements.
  - FieldSafetyCorrectiveAction → hasPurpose some PreventiveCorrectiveAction
    Rationale: The text defines 'field safety corrective action' as a corrective action taken by the manufacturer to prevent or reduce the risk of a serious incident, which aligns with the purpose of preventive and corrective actions.
  - FieldSafetyCorrectiveAction → hasLegalBasis some RegulationAmendmentRestriction
    Rationale: The text mentions Regulation 44ZC(1) which implies a legal basis for field safety corrective actions.
  - FieldSafetyCorrectiveAction → hasRiskAssessment some RiskAssessment
    Rationale: The text implies that field safety corrective actions are taken to prevent or reduce risks, which requires a risk assessment.
  - PostMarketSurveillance → hasLegalBasis some RegulationAmendmentRestriction
    Rationale: The requirements of this Part apply in respect of relevant devices as per Regulation 44ZD(1).
  - RegulatoryExemption → hasLegalBasis some UnionLawException
    Rationale: The text states 'This Part does not apply to' certain devices, implying a legal basis for exemption.
  - RegulatoryExemption → hasLegalBasis some ExceptionToPostMarketSurveillance
    Rationale: The regulation text explicitly mentions exemptions related to post-market surveillance.
  - DeviceType → hasRisk some RiskAssessment
    Rationale: The manufacturer must ensure the PMS system is proportionate to the risk posed by the device.
  - DeviceType → hasPurpose some PostMarketSurveillance
    Rationale: The PMS system includes the analysis of data relevant to the quality, performance and safety of the device throughout its lifetime.
  - TrendInIncidents → hasPurpose some TrendInvestigation
    Rationale: The manufacturer must ensure that the PMS system is used throughout the PMS period to identify trends in incidents.
  - TrendInIncidents → hasObligation some ManufacturerPostMarketObligation
    Rationale: The manufacturer must ensure that the PMS system is used throughout the PMS period to identify trends in incidents.
  - TrendInIncidents → hasRiskAssessment some RiskAssessment
    Rationale: The manufacturer must ensure that the PMS system is used throughout the PMS period to identify trends in incidents, including those on which the manufacturer must report under regulation 44ZN (trend reporting).
  - ExceptionToPostMarketSurveillance → hasLegalBasis some RegulationAmendmentRestriction
    Rationale: The regulatory text mentions exceptions to post-market surveillance based on specific regulations.
  - ExceptionToPostMarketSurveillance → hasLegalBasis some UnionLawException
    Rationale: The regulatory text mentions exceptions to post-market surveillance based on specific regulations.
  - ExceptionToPostMarketSurveillance → hasLegalBasis some RegulatoryExemption
    Rationale: The regulatory text mentions exceptions to post-market surveillance based on specific regulations.
  - PostMarketSurveillanceReport → hasObligation some ManufacturerPostMarketObligation
    Rationale: The manufacturer and the UK responsible person must provide the PMS plan, including post-market surveillance reports.
  - ApprovedBodyReport → hasObligation some ManufacturerPostMarketObligation
    Rationale: The manufacturer and the UK responsible person must provide reports issued by an approved body.
  - PostMarketSurveillanceReport → hasRight some RequestForPostMarketSurveillanceInformation
    Rationale: The Secretary of State can request post-market surveillance reports.
  - ApprovedBodyReport → hasRight some RequestForPostMarketSurveillanceInformation
    Rationale: The Secretary of State can request reports issued by an approved body.
  - RiskIdentification → hasRisk some RiskAssessment
    Rationale: The manufacturer identifies a risk that following evaluation is deemed to compromise the performance or safety of the device.
  - DeviceNonConformity → hasRisk some RiskAssessment
    Rationale: The device is not in conformity with the relevant essential requirements.
  - RiskIdentification → isMitigatedByMeasure some PreventiveCorrectiveAction
    Rationale: The manufacturer must take the necessary preventive or corrective action as soon as possible to reduce that risk.
  - DeviceNonConformity → isMitigatedByMeasure some PreventiveCorrectiveAction
    Rationale: The manufacturer must take the necessary preventive or corrective action as soon as possible to bring the device into conformity.
  - UKResponsiblePerson → hasNotice some PostMarketSurveillance
    Rationale: The manufacturer must notify the action to the UK responsible person.
  - PostMarketSurveillanceNotificationReview → hasLegalBasis some RegulationAmendmentRestriction
    Rationale: The review is conducted under Regulation 44ZG(3) of the UK MDR 2002.
  - TimeSensitiveReporting → hasObligation some ManufacturerPostMarketObligation
    Rationale: The regulation states that the report must be submitted no later than 2 days after the manufacturer becomes aware of the threat, implying an obligation on the manufacturer.
  - SeriousDeterioration → hasLegalBasis some RegulationAmendmentRestriction
    Rationale: Regulation 44ZH(5) of UK MDR 2002 explicitly requires reporting of unanticipated serious deterioration.
  - ApprovedBodyInformation → hasObligation some RequestForPostMarketSurveillanceInformation
    Rationale: The approved body is required to provide information and assessments relevant to the serious incident and field safety corrective action.
  - SeparateInvestigation → hasPurpose some RiskAssessment
    Rationale: The Secretary of State may initiate a separate investigation.
  - ManufacturerCooperation → hasObligation some RequestForPostMarketSurveillanceInformation
    Rationale: The regulation states that a manufacturer must cooperate with the Secretary of State in relation to investigations.
  - TimelyResponse → hasObligation some RequestForPostMarketSurveillanceInformation
    Rationale: The regulation states that upon request, the manufacturer must provide updates and documents within 3 working days.
  - DeviceAlterationRestriction → hasObligation some PostMarketSurveillanceInvestigation
    Rationale: The regulation states that a manufacturer must not perform any investigation which involves altering the device or a sample of the batch concerned before informing the Secretary of State.
  - DeviceDescription → hasRiskAssessment some RiskAssessment
    Rationale: The initial report must include the justification for the manufacturer’s chosen FSCA, based on the conclusions of the risk assessment produced under paragraph (1)(a).
  - ManufacturerSubmission → hasObligation some PostMarketSurveillance
    Rationale: The manufacturer must submit a final report to demonstrate the effectiveness of the action.
  - ManufacturerSubmission → hasPurpose some PostMarketSurveillance
    Rationale: The submission is for the purpose of post-market surveillance.
  - DeviceModel → hasObligation some ManufacturerPostMarketObligation
    Rationale: The regulation states that a manufacturer of a device placed on the market or put into service in Great Britain must report to the Secretary of State when taking any field safety corrective action outside Great Britain.
  - DeviceUser → hasLegalBasis some UKResponsiblePerson
    Rationale: The report must include the UK responsible person's name and contact details (if there is one).
  - EstimatedNumberOfUsers → hasLegalBasis some PostMarketSurveillance
    Rationale: The report must include the estimated number of users as part of post-market surveillance report.
  - DevicePlacementOnMarket → hasLegalBasis some RegulationAmendmentRestriction
    Rationale: The regulation states that devices are placed on the market in accordance with specific regulations.
  - DeviceClassification → hasLegalBasis some MedicalDeviceClassification
    Rationale: The regulation classifies devices under specific directives and regulations.
  - ClassIDevice → hasLegalBasis some ClassIDevice
    Rationale: The regulation explicitly mentions class I devices under Directive 93/42 and Regulation (EU) 2017/745.
  - ClassAorBDevice → hasLegalBasis some MedicalDeviceClassification
    Rationale: The regulation mentions devices classified as A or B under Regulation (EU) 2017/746.
  - CorrectiveAction → hasPurpose some ExceptionalCase
    Rationale: The text mentions 'a description of any ... corrective action that has been taken by the manufacturer'
  - PreventiveAction → hasPurpose some ExceptionalCase
    Rationale: The text mentions 'a description of any preventive or corrective action'
  - CorrectiveAction → isMitigatedByMeasure some RiskMitigationSafeguard
    Rationale: The text implies corrective action is taken in relation to device risks
  - PreventiveAction → isMitigatedByMeasure some RiskMitigationSafeguard
    Rationale: The text implies preventive action is taken in relation to device risks
  - PostMarketSurveillancePeriod → hasObligation some ManufacturerPostMarketObligation
    Rationale: The PMSR must be produced within 3 years of the device being placed on the market or put into service and updated at least every 3 years.
  - UKCAmarking → hasLegalBasis some RegulatoryExemption
    Rationale: The regulation mentions 'a medical device which does not bear a UKCA marking'.
  - Compatibility → hasLegalBasis some ExceptionToPostMarketSurveillance
    Rationale: The regulation states 'the chosen combination of medical devices is not compatible in view of their original intended use'.
  - PreventiveCorrectiveAction → hasLegalBasis some RegulationAmendmentRestriction
    Rationale: The text mentions 'any preventive or corrective action' in relation to Regulation 44ZL(5) which implies a legal basis.
  - DeclarationOfConformity → hasLegalBasis some ConformityAssessmentProcedure
    Rationale: The text mentions 'declaration of conformity' in relation to devices which implies a legal basis in conformity assessment procedures.
  - DeviceCertificate → hasLegalBasis some ConformityDeclaration
    Rationale: The text mentions 'certificate that was issued by an approved body or notified body' which implies a legal basis in conformity declarations.
  - DeviceUserPopulation → hasRiskAssessment some RiskAssessment
    Rationale: The PSUR must include the required risk analysis; this implies a risk assessment for the device user population.
  - DeviceUserPopulation → hasPurpose some PostMarketSurveillance
    Rationale: The PSUR is a part of post-market surveillance, implying that the purpose of the device user population data is for post-market surveillance.
  - PostMarketSurveillanceUpdateReport → hasObligation some ManufacturerPostMarketObligation
    Rationale: The manufacturer must submit the PSUR and each updated PSUR.
  - ConformityAssessmentProcedure → hasObligation some PostMarketSurveillanceUpdateReport
    Rationale: The approved body must take into account the PSUR and updated PSURs when carrying out its surveillance activities.
  - WorkingDayResponseTime → hasLegalBasis some RegulationAmendmentRestriction
    Rationale: The regulation text mentions 'Regulation 44ZM(13)' which implies a legal basis for the working day response time.
  - WorkingDayResponseTime → hasObligation some ManufacturerPostMarketObligation
    Rationale: The text mentions that the approved body 'must provide a copy of its completed reports' implying an obligation related to post-market surveillance.
  - WorkingDayResponseTime → hasRight some RightToRequestAccess
    Rationale: The Secretary of State has the right to request reports within 3 working days.
  - StatisticalMethodology → hasRiskAssessment some RiskAssessment
    Rationale: The statistical methodology is set out in the post-market surveillance plan to determine a significant increase in incidents.
  - ErroneousResults → hasRisk some PostMarketSurveillance
    Rationale: The text mentions 'significant increase in expected erroneous results' in relation to post-market surveillance.
  - TrendInformation → hasLegalBasis some RegulationAmendmentRestriction
    Rationale: Regulation 44ZN(5) explicitly requires an initial report under this regulation.
  - TrendInformation → hasPurpose some PostMarketSurveillance
    Rationale: The initial report is required for post-market surveillance.
  - PostMarketSurveillanceUpdate → hasObligation some ManufacturerPostMarketObligation
    Rationale: The manufacturer must provide updates relevant to the investigation.
  - PostMarketSurveillanceDocument → hasObligation some ManufacturerPostMarketObligation
    Rationale: The manufacturer must provide documents relevant to the investigation.
  - RequestForPostMarketSurveillanceInformation → hasRight some RightToRequestAccess
    Rationale: The Secretary of State has the right to request information.
  - TimeframeForProvidingPostMarketSurveillanceInformation → hasObligation some SecretaryOfStateNotification
    Rationale: The manufacturer must respond within 3 working days of the request.
  - SafetyConcern → hasRiskAssessment some RiskAssessment
    Rationale: The Secretary of State must have processes for monitoring information to identify trends, patterns or signals that may reveal new risks or safety concerns, implying a need for risk assessments.
  - ManufacturerInvestigation → hasObligation some ManufacturerPostMarketObligation
    Rationale: The manufacturer must investigate the risk or safety concern and submit a report to the Secretary of State as soon as possible.
  - ManufacturerInvestigation → hasPurpose some PostMarketSurveillance
    Rationale: The manufacturer must investigate the risk or safety concern for post-market surveillance purposes.
  - ManufacturerInvestigation → hasRiskAssessment some RiskAssessment
    Rationale: The manufacturer must investigate the risk or safety concern and submit a report setting out the methods and conclusions of the manufacturer’s investigation.
  - ManufacturerInvestigation → hasTechnicalOrganisationalMeasure some PreventiveCorrectiveAction
    Rationale: The manufacturer must submit a report setting out any preventive action or corrective action the manufacturer has taken or intends to take.
  - RetentionPeriod → hasLegalBasis some RegulationAmendmentRestriction
    Rationale: The regulatory text mentions 'the period set out in paragraph (2)' which implies a legal basis for retention.
  - RetentionPeriod → hasPurpose some PostMarketSurveillance
    Rationale: The documentation is retained 'for the purposes of this Part' which relates to post-market surveillance.
  - TaskVariation → hasLegalBasis some RegulationAmendmentRestriction
    Rationale: The Secretary of State may vary the tasks that an approved body may carry out, according to Regulation 44ZP(4).
  - ApprovedBodyDesignation → hasLegalBasis some DesignationRestriction
    Rationale: The tasks which an approved body is designated to carry out may be varied by the Secretary of State according to Regulation 44ZP(4).
  - DesignationRestriction → hasLegalBasis some ApplicableCriteria
    Rationale: The Secretary of State considers that it is no longer a body in respect of which the applicable criteria for designation set out in Annex 8 of Directive 90/385, Annex XI of Directive 93/42, both read with Regulation (EU) No 722/2012 or Annex IX of Directive 98/79 are met.
  - DesignationWithdrawal → hasLegalBasis some ApplicableCriteria
    Rationale: the Secretary of State considers that it is no longer a body in respect of which the applicable criteria for designation set out in Annex 8 of Directive 90/385, Annex XI of Directive 93/42, both read with Regulation (EU) No 722/2012 or Annex IX of Directive 98/79 are met
  - RepresentationOpportunity → hasLegalBasis some RegulationAmendmentRestriction
    Rationale: The regulatory text mentions 'Regulation 44ZP(6)' which implies a legal basis for the representation opportunity.
  - RepresentationOpportunity → hasPurpose some PostMarketSurveillance
    Rationale: The representation opportunity is provided before effecting a variation or restricting/withdrawing a designation, which is related to post-market surveillance.
  - BodyCriteriaAssessment → hasLegalBasis some RegulationAmendmentRestriction
    Rationale: The regulatory text mentions 'Annex 8 of Directive 90/385, Annex XI of Directive 93/42, both read with Regulation (EU) No 722/2012 or Annex IX of Directive 98/79' as the legal basis for assessing body criteria.
  - BodyCriteriaAssessment → hasLegalBasis some UnionLawException
    Rationale: The regulatory text implies that the Secretary of State's decision is based on Union law exceptions for body criteria assessment.
  - ManufacturerInspection → hasLegalBasis some PostMarketSurveillance
    Rationale: The regulatory text mentions 'Regulation 44ZP(7) — Post-market surveillance' as the legal basis for manufacturer inspection.
  - ApprovedBodyInformationRequest → hasLegalBasis some RegulationAmendmentRestriction
    Rationale: The Secretary of State's request for information from an approved body is based on Regulation 44ZP(8) of the UK MDR 2002.
  - ApprovedBodyInformationRequest → hasPurpose some PostMarketSurveillance
    Rationale: The request for information is necessary for post-market surveillance purposes as stated in Regulation 44ZP(8) of the UK MDR 2002.
  - InvasiveDevice → hasPurpose some MedicalDeviceClassification
    Rationale: The invasive device is intended to penetrate inside the body, which aligns with the purpose of a medical device classification.
  - FalsifiedDevice → hasRisk some RiskAssessment
    Rationale: A falsified device poses a risk to health and safety, which is assessed through a risk assessment.
  - DeviceDesign → hasLegalBasis some EUdatabaseRegistrationObligation
    Rationale: Manufacturers shall ensure devices are designed in accordance with the requirements of this Regulation.
  - DeviceManufacturing → hasLegalBasis some EUdatabaseRegistrationObligation
    Rationale: Manufacturers shall ensure devices are manufactured in accordance with the requirements of this Regulation.
  - DeviceDesign → hasLegalBasis some ConformityAssessmentProcedure
    Rationale: Devices must be designed in accordance with the requirements of this Regulation, implying a conformity assessment procedure.
  - DeviceManufacturing → hasLegalBasis some ConformityAssessmentProcedure
    Rationale: Devices must be manufactured in accordance with the requirements of this Regulation, implying a conformity assessment procedure.
  - DeviceTechnicalDocumentation → hasLegalBasis some AnnexII
    Rationale: The technical documentation shall include the elements set out in Annexes II and III.
  - DeviceTechnicalDocumentation → hasLegalBasis some AnnexIII
    Rationale: The technical documentation shall include the elements set out in Annexes II and III.
  - InvestigationalDevice → hasObligation some ConformityAssessmentProcedure
    Rationale: Devices that are investigational are excluded from drawing up an EU declaration of conformity and affixing the CE marking following the applicable conformity assessment procedure.
  - CEMarkingOfConformity → hasLegalBasis some ConformityDeclaration
    Rationale: The CE marking of conformity is drawn up in accordance with Article 20 and is based on the EU declaration of conformity according to Article 19.
  - TechnicalDocumentationRetention → hasLegalBasis some EUDeclarationOfConformity
    Rationale: The technical documentation must be kept available for the competent authorities for a period of at least 10 years after the last device covered by the EU declaration of conformity has been placed on the market.
  - EUDeclarationOfConformityRetention → hasLegalBasis some ConformityDeclaration
    Rationale: The EU declaration of conformity must be kept available for the competent authorities for a period of at least 10 years after the last device covered by it has been placed on the market.
  - CertificateRetention → hasLegalBasis some ConformityAssessmentProcedure
    Rationale: The certificate, including any amendments and supplements, issued in accordance with Article 56, must be kept available for the competent authorities.
  - DeviceModificationManagement → hasObligation some QualityManagementSystem
    Rationale: Manufacturers shall establish, document, implement, maintain, keep up to date and continually improve a quality management system.
  - DeviceModificationManagement → hasTechnicalOrganisationalMeasure some ModificationManagementProcedure
    Rationale: Manufacturers shall ensure that procedures are in place to keep series production in conformity with the requirements of this Regulation.
  - ConformityDeclaration → hasObligation some QualityManagementSystem
    Rationale: Manufacturers shall establish, document, implement, maintain, keep up to date and continually improve a quality management system that shall ensure compliance with this Regulation.
  - DeviceDesignChange → hasRiskAssessment some RiskManagementSystem
    Rationale: Changes in device design or characteristics and changes in the harmonised standards or CS by reference to which the conformity of a device is declared shall be adequately taken into account in a timely manner.
  - ConformityDeclaration → hasTechnicalOrganisationalMeasure some RiskManagementSystem
    Rationale: The quality management system shall address at least the following aspects: identification of applicable general safety and performance requirements and exploration of options to address those requirements.
  - ManagementResponsibility → hasObligation some QualityManagementSystem
    Rationale: The regulation states that manufacturers shall establish, document, implement, maintain, keep up to date and continually improve a quality management system.
  - DeviceCharacteristicChange → hasObligation some ModificationManagementProcedure
    Rationale: Manufacturers shall ensure that procedures are in place to keep series production in conformity with the requirements of this Regulation. Changes in device design or characteristics shall be adequately taken into account in a timely manner.
  - PostMarketClinicalFollowUp → hasObligation some ClinicalEvaluation
    Rationale: The quality management system shall address at least the following aspects: clinical evaluation in accordance with Article 61 and Annex XIV, including PMCF;
  - Quality_Management_System → hasLegalBasis some RegulationAmendmentRestriction
    Rationale: The regulation requires manufacturers to establish, document, implement, maintain, keep up to date and continually improve a quality management system that ensures compliance with this Regulation.
  - Quality_Management_System → hasObligation some ManufacturerPostMarketObligation
    Rationale: Manufacturers shall ensure that procedures are in place to keep series production in conformity with the requirements of this Regulation.
  - Conformity_Assessment_Procedure → hasLegalBasis some UnionLawException
    Rationale: Changes in device design or characteristics and changes in the harmonised standards or CS by reference to which the conformity of a device is declared shall be adequately taken into account in a timely manner.
  - HarmonisedStandardsChange → hasObligation some QualityManagementSystem
    Rationale: The regulation requires manufacturers to establish, document, implement, maintain, keep up to date and continually improve a quality management system.
  - DeviceWithdrawal → hasLegalBasis some RegulatoryExemption
    Rationale: The regulation states that manufacturers shall withdraw a device if it's not in conformity.
  - DeviceRecall → hasLegalBasis some RegulatoryExemption
    Rationale: The regulation states that manufacturers shall recall a device if it's not in conformity.
  - DeviceWithdrawal → hasObligation some ManufacturerPostMarketObligation
    Rationale: The regulation states that manufacturers have an obligation to withdraw a device.
  - DeviceRecall → hasObligation some ManufacturerPostMarketObligation
    Rationale: The regulation states that manufacturers have an obligation to recall a device.
  - IncidentRecordingSystem → hasLegalBasis some ManufacturerPostMarketObligation
    Rationale: The text mentions 'as described in Articles 87 and 88' which implies a legal basis for the obligation.
  - IncidentRecordingSystem → hasObligation some PostMarketSurveillance
    Rationale: The text states 'Manufacturers shall have a system for recording and reporting of incidents and field safety corrective actions' which implies an obligation for post-market surveillance.
  - DeviceDocumentation → hasLegalBasis some EUdatabaseRegistrationObligation
    Rationale: Manufacturers shall provide competent authority with all information and documentation necessary to demonstrate conformity of the device.
  - DeviceDocumentation → hasLegalBasis some ManufacturerPostMarketObligation
    Rationale: Manufacturers shall cooperate with competent authority on corrective actions to eliminate or mitigate risks posed by devices.
  - DeviceSample → hasLegalBasis some ConformityAssessmentProcedure
    Rationale: Competent authority may require manufacturer to provide samples of the device free of charge.
  - DeviceRestriction → hasLegalBasis some DeviceWithdrawal
    Rationale: Competent authority may prohibit or restrict device's being made available on its national market or withdraw device from market.
  - ClinicalEvaluation → hasRiskAssessment some RiskAssessment
    Rationale: Clinical evaluation shall be based on clinical data providing sufficient clinical evidence, including where applicable relevant data as referred to in Annex III, to confirm conformity with relevant general safety and performance requirements.
  - BenefitRiskRatio → hasRiskAssessment some RiskAssessment
    Rationale: The evaluation of the undesirable side-effects and of the acceptability of the benefit-risk-ratio shall be based on clinical data.
  - ScientificLiteratureEvaluation → hasLegalBasis some ClinicalEvaluation
    Rationale: The clinical evaluation shall follow a defined and methodologically sound procedure based on the relevant scientific literature.
  - ClinicalEvaluationProcedure → hasPurpose some ClinicalEvaluation
    Rationale: A clinical evaluation shall follow a defined and methodologically sound procedure based on the following.
  - ClinicalInvestigationExemption → hasLegalBasis some RegulatoryExemption
    Rationale: The clinical investigation exemption is based on specific regulatory conditions outlined in Article 61(4) of EU MDR 2017/745.
  - DeviceModification → hasLegalBasis some NotifiedBodyApprovedChange
    Rationale: Device modifications must be approved by a notified body according to Section 3 of Annex XIV.
  - EquivalenceDemonstration → hasLegalBasis some ClinicalEvaluation
    Rationale: The demonstration of equivalence relies on a clinical evaluation as per Section 3 of Annex XIV.
  - DeviceEquivalence → hasLegalBasis some ClinicalEvaluation
    Rationale: The regulation states that a manufacturer of a device demonstrated to be equivalent to an already marketed device may rely on paragraph 4 if certain conditions are fulfilled, implying a legal basis in clinical evaluation.
  - OriginalClinicalEvaluation → hasLegalBasis some ClinicalEvaluation
    Rationale: The regulation explicitly requires that the original clinical evaluation has been performed in compliance with the requirements of this Regulation.
  - Suture → hasLegalBasis some ClinicalEvaluation
    Rationale: The clinical evaluation is based on sufficient clinical data and is in compliance with the relevant product-specific CS.
  - Staple → hasLegalBasis some ClinicalEvaluation
    Rationale: The clinical evaluation is based on sufficient clinical data and is in compliance with the relevant product-specific CS.
  - DentalFilling → hasLegalBasis some ClinicalEvaluation
    Rationale: The clinical evaluation is based on sufficient clinical data and is in compliance with the relevant product-specific CS.
  - DentalBrace → hasLegalBasis some ClinicalEvaluation
    Rationale: The clinical evaluation is based on sufficient clinical data and is in compliance with the relevant product-specific CS.
  - ToothCrown → hasLegalBasis some ClinicalEvaluation
    Rationale: The clinical evaluation is based on sufficient clinical data and is in compliance with the relevant product-specific CS.
  - ProductSpecificCS → hasLegalBasis some ClinicalEvaluation
    Rationale: The clinical evaluation is based on sufficient clinical data and is in compliance with the relevant product-specific CS.
  - ExemptedDevice → hasLegalBasis some DelegatedActs
    Rationale: The Commission is empowered to adopt delegated acts to amend the list of exempted devices.
  - AnalogousMedicalDevice → hasLegalBasis some ClinicalEvaluation
    Rationale: Clinical evaluations of products without an intended medical purpose listed in Annex XVI shall be based on relevant data concerning safety, including data from post-market surveillance, PMCF, and, where applicable, specific clinical investigation, and may rely on existing clinical data from an analogous medical device.
  - JustificationForException → hasRiskAssessment some RiskAssessment
    Rationale: The regulatory text mentions 'based on the results of the manufacturer's risk management'.
  - DeviceHumanInteraction → hasRisk some RiskManagementSystem
    Rationale: The text considers 'the specifics of the interaction between the device and the human body'.
  - ManufacturerClaim → hasObligation some ConformityDeclaration
    Rationale: The text mentions 'the claims of the manufacturer' in relation to demonstrating conformity.
  - PMCFPlan → hasPurpose some PostMarketSurveillance
    Rationale: The PMCF plan is implemented in accordance with Part B of Annex XIV and the post-market surveillance plan referred to in Article 84.
  - PMCFEvaluationReport → hasLegalBasis some ClinicalEvaluation
    Rationale: The PMCF evaluation report is updated with clinical data obtained from the implementation of the manufacturer's PMCF plan.
  - ImplementingActs → hasLegalBasis some AnnexXIV
    Rationale: The Commission may adopt implementing acts to the extent necessary to resolve issues of divergent interpretation and of practical application of Annex XIV.
  - UniformApplication → hasLegalBasis some AnnexXIV
    Rationale: The Commission may adopt implementing acts to ensure the uniform application of Annex XIV.
  - DeviceLifecycle → hasObligation some PostMarketSurveillance
    Rationale: The post-market surveillance system shall be suited to actively and systematically gathering, recording and analysing relevant data on the quality, performance and safety of a device throughout its entire lifetime.
  - BenefitRiskDeterminationUpdate → hasPurpose some RiskManagementSystem
    Rationale: The text mentions 'to update the benefit-risk determination and to improve the risk management'.
  - DesignUpdate → hasPurpose some PostMarketSurveillance
    Rationale: Data gathered by the manufacturer's post-market surveillance system shall be used to update the design and manufacturing information.
  - ManufacturingInformationUpdate → hasPurpose some PostMarketSurveillance
    Rationale: Data gathered by the manufacturer's post-market surveillance system shall be used to update the design and manufacturing information.
  - LabellingUpdate → hasPurpose some PostMarketSurveillance
    Rationale: Data gathered by the manufacturer's post-market surveillance system shall be used to update the instructions for use and the labelling.
  - UsabilityImprovement → hasPurpose some RiskManagementSystem
    Rationale: Data gathered by the manufacturer's post-market surveillance system shall in particular be used: (f) for the identification of options to improve the usability, performance and safety of the device;
  - UsabilityImprovement → hasPurpose some PostMarketSurveillance
    Rationale: Data gathered by the manufacturer's post-market surveillance system shall in particular be used: (f) for the identification of options to improve the usability, performance and safety of the device;
  - ManufacturerPostMarketObligation → hasPurpose some PostMarketSurveillance
    Rationale: The text states that data gathered by the manufacturer's post-market surveillance system shall be used for post-market surveillance of other devices.
  - UnionMarketDevice → hasObligation some ManufacturerPostMarketObligation
    Rationale: Manufacturers of devices made available on the Union market shall report to the relevant competent authorities.
  - SeriousIncidentReport → hasLegalBasis some ManufacturerPostMarketObligation
    Rationale: The text states that the report shall be provided immediately after the manufacturer has established or as soon as it suspects a causal relationship between the device and the serious incident.
  - SeriousIncidentTiming → hasLegalBasis some ManufacturerPostMarketObligation
    Rationale: The text specifies that the report shall be provided not later than 10 days after the date on which the manufacturer becomes aware of the serious incident.
  - UnanticipatedSeriousDeterioration → hasRiskAssessment some RiskAssessment
    Rationale: The text implies that an assessment of the serious deterioration is required to determine the causal relationship with the device.
  - InitialReport → hasObligation some ManufacturerPostMarketObligation
    Rationale: The manufacturer may submit an initial report that is incomplete.
  - CompleteReport → hasObligation some ManufacturerPostMarketObligation
    Rationale: The manufacturer shall follow up with a complete report.
  - TargetedInformationCampaign → hasPurpose some HumanInvolvementForOversight
    Rationale: The text mentions 'to encourage and enable healthcare professionals, users and patients to report to the competent authorities suspected serious incidents' which implies the purpose of targeted information campaigns is to facilitate human involvement in oversight.
  - ExpectedUndesirableSideEffect → hasLegalBasis some ManufacturerPostMarketObligation
    Rationale: The text states that an explanatory statement is provided if the manufacturer considers the incident is not a serious incident or is an expected undesirable side-effect, implying a legal basis for obligations.
  - FaultCondition → hasRisk some RiskAssessment
    Rationale: Devices that incorporate electronic programmable systems, including software, or software that are devices in themselves, shall be designed to ensure repeatability, reliability and performance in line with their intended use. In the event of a single fault condition, appropriate means shall be adopted to eliminate or reduce as far as possible consequent risks or impairment of performance.
  - FaultCondition → isMitigatedByMeasure some RiskManagementMeasure
    Rationale: In the event of a single fault condition, appropriate means shall be adopted to eliminate or reduce as far as possible consequent risks or impairment of performance.
  - PerformanceImpairment → hasRisk some RiskAssessment
    Rationale: Devices that incorporate electronic programmable systems, including software, or software that are devices in themselves, shall be designed to ensure repeatability, reliability and performance in line with their intended use. In the event of a single fault condition, appropriate means shall be adopted to eliminate or reduce as far as possible consequent risks or impairment of performance.
  - Repeatability → hasTechnicalMeasure some DesignationRestriction
    Rationale: Devices that incorporate electronic programmable systems, including software, or software that are devices in themselves, shall be designed to ensure repeatability, reliability and performance in line with their intended use.
  - SoftwareSecurity → hasRiskAssessment some RiskManagementSystem
    Rationale: The regulatory text mentions 'risk management' as a principle for software development.
  - SoftwareSecurity → hasTechnicalOrganisationalMeasure some DataSecurityManagement
    Rationale: The regulatory text mentions 'information security' and 'verification and validation' as aspects of software development.
  - SoftwareSecurity → hasRisk some RiskAssessment
    Rationale: The regulatory text mentions 'risk management' including 'information security'.
  - MobileComputingPlatform → hasRisk some VaryingEnvironment
    Rationale: The text mentions 'varying environment as regards level of light or noise' which implies a risk associated with mobile computing platforms.
  - MobileComputingPlatform → hasTechnicalMeasure some PrivacyByDesign
    Rationale: The text implies that software should be designed taking into account specific features of mobile platforms, suggesting a technical measure for privacy by design.
  - UnauthorisedAccessProtection → hasTechnicalMeasure some DataSecurityManagement
    Rationale: Manufacturers shall set out minimum requirements concerning IT security measures, including protection against unauthorised access, necessary to run the software as intended.
  - ClassIIaSoftware → hasLegalBasis some MedicalDeviceClassification
    Rationale: Software intended to provide information which is used to take decisions with diagnosis or therapeutic purposes is classified as class IIa.
  - ClassIIbSoftware → hasLegalBasis some MedicalDeviceClassification
    Rationale: Software intended to provide information which is used to take decisions with diagnosis or therapeutic purposes and may cause a serious deterioration of a person's state of health or a surgical intervention is classified as class IIb.
  - ClassIIIsoftware → hasLegalBasis some MedicalDeviceClassification
    Rationale: Software intended to provide information which is used to take decisions with diagnosis or therapeutic purposes and may cause death or an irreversible deterioration of a person's state of health is classified as class III.
  - SignificantImpactAssessment → hasRiskAssessment some RiskAssessment
    Rationale: The regulatory text mentions conditions for automated decision-making which implies a risk assessment.
  - ContractPerformanceCondition → hasLegalBasis some LawfulAIExceptions
    Rationale: The text mentions 'necessary for entering into, or performing, a contract between the data subject and a controller' which implies a legal basis for processing.
  - Article9Point2GCondition → hasLegalBasis some Article9Point2GCondition
    Rationale: point (g) of Article 9(2) applies.
  - ControllerIntervention → hasPurpose some HumanInvolvementForOversight
    Rationale: The safeguards must enable the data subject to obtain human intervention on the part of the controller in relation to such decisions.
  - DecisionContestabilityMeasure → hasPurpose some DataSubjectConsultation
    Rationale: The safeguards must enable the data subject to contest such decisions.
  - HumanInvolvementRegulation → hasLegalBasis some AutomatedDecisionMaking
    Rationale: The Secretary of State may by regulations provide that, for the purposes of Article 22A(1)(a), there is, or is not, to be taken to be meaningful human involvement in the taking of a decision.
  - AdditionalSafeguardMeasure → hasLegalBasis some RegulationAmendmentRestriction
    Rationale: The Secretary of State may by regulations make provision about safeguards.
  - AdditionalSafeguardMeasure → hasPurpose some RiskMitigationSafeguard
    Rationale: provision requiring the safeguards to include measures in addition to those described in Article 22C(2)
  - ExcludedMeasures → hasLegalBasis some RegulatoryExemption
    Rationale: The Secretary of State may by regulations make provision about measures which are not to be taken to satisfy Article 22C(2) under Article 22D(3)(c).
  - SensitiveProcessing → hasLegalBasis some ExplicitConsentBasedDecision
    Rationale: Regulations under Article 50B(2) allow decisions based entirely on processing of personal data to which the data subject has given explicit consent.
  - SensitiveProcessing → hasLegalBasis some LawfulAIExceptions
    Rationale: Regulations under Article 50B(3) allow decisions required or authorised by law.
  - Article22CRequirement → hasLegalBasis some TransparencyObligation
    Rationale: The text amends Articles 13(2)(f) and 14(2)(g) to refer to Article 22C, which requires safeguards for automated decision-making, implying a legal basis for transparency obligations.

## Raw LLM responses
Saved to: D:\KEP_FALL\KEP_FALL\OUT_CANDIDATES\llm_restrictions_raw.json
