"""Legacy UI/CLI result shape backed by the same Athena policy."""
def legacy(result):
    r = result.model_dump(mode='json')
    findings = r['findings']
    return {**r, 'decision': 'allowed' if r['permitted'] else 'blocked',
            'athena_decision': r['decision'], 'blocked': not r['permitted'],
            'reasons': [f['description'] for f in findings] or ['All required checks cleared.'],
            'layers': {
                'normalization': {'transforms': [f['description'] for f in findings if f['source'] in {'encoding_shield', 'normalization_shield'}],
                                  'decoded': r['decoded_variants'], 'clean_preview': (r['normalized_variants'] or [r['original_text']])[0][:300]},
                'aggregation': {'turns_considered': r['session']['turns_considered'], 'prior_turns': [],
                                'effective_intent_preview': r['session']['security_summary']},
                'policy': {'fail_open': False, 'guard_partial': any(g.get('status') == 'partial' for g in r['guard_results']),
                           'guard_unavailable': any(not g.get('ok') for g in r['guard_results'])},
                'local_detector': {'flagged': any(f['category'] in {'injection','session_injection'} for f in findings), 'matches': []}},
            'guard_on_submitted': r['guard_results'][-1], 'submitted_text_preview': r['original_text'][:300]}
