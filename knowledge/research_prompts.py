"""Deep Research prompt templates — extracted from deep_research.py for maintainability."""

QUERY_ANALYSIS_PROMPT = """You are a research architect. Analyze this question and decompose it.

**Question:** {question}

Return a JSON object:
{{
  "main_topic": "The core subject",
  "sub_questions": ["Q1", "Q2", "Q3", ...],  // 3-6 sub-questions
  "key_topics": ["topic1", "topic2", ...],
  "search_queries": ["query1", "query2", ...],  // 3-5 concrete search queries
  "required_perspectives": ["perspective1", ...],
  "success_criteria": "When is the answer complete?"
}}"""

PARALLEL_SEARCH_PROMPT = """Generate {count} parallel search queries for this sub-question.
Each query should target a different angle or source type.

**Sub-question:** {sub_question}

Return JSON array: ["query1", "query2", "query3", ...]"""

CROSS_REFERENCE_PROMPT = """Cross-reference the following findings from multiple searches.
Identify: common themes, contradictions, unique insights, and gaps.

**Question:** {question}

**Findings:**
{findings}

Return JSON:
{{
  "common_themes": ["theme1", ...],
  "contradictions": [{{"claim_a": "...", "claim_b": "..."}}, ...],
  "unique_insights": ["insight1", ...],
  "gaps": ["gap1", ...],
  "confidence_score": 0.0-1.0
}}"""

SYNTHESIS_PROMPT = """Synthesize these research findings into a coherent answer.

**Question:** {question}

**Cross-reference Analysis:**
{cross_ref}

**All Findings:**
{findings}

**Instructions:**
1. Start with a concise executive summary
2. Cover each key topic with evidence
3. Note contradictions and uncertainties
4. End with conclusions and confidence level
5. Include specific facts, numbers, and sources"""

FINAL_REPORT_PROMPT = """Write a final comprehensive research report.

**Question:** {question}

**Synthesized Content:**
{synthesis}

**Requirements:**
- Executive summary at top
- Well-structured sections with headers
- Specific facts, data, and quotes with sources
- Note uncertainties and limitations
- Confidence assessment
- Follow-up questions if any
- Length: comprehensive but concise"""
