from whitebox.bundles import bundle_hash, canonical_bundle_payload
from whitebox.models import SkillBundle


def test_bundle_hash_is_independent_of_skill_order() -> None:
    base = {
        "format": "whitebox.skill-bundle", "version": 1,
        "name": "test", "description": "",
        "skills": [
            {"name": name, "description": name, "execution_mode": "context", "instructions": name,
             "metadata": {}, "capabilities": [], "parameters_schema": {}, "content_hash": name * 8}
            for name in ("alpha", "beta")
        ],
        "node_templates": [],
    }
    first = SkillBundle.model_validate(base)
    second = SkillBundle.model_validate({**base, "skills": list(reversed(base["skills"]))})
    assert bundle_hash(first) == bundle_hash(second)
    assert canonical_bundle_payload(first) == canonical_bundle_payload(second)
