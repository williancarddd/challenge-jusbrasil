"""
Phase 4: Optimization - Analyze confidence calibration accuracy.
"""

import sys
import json
from pathlib import Path
from collections import defaultdict
sys.path.insert(0, "src")

from challenge_jusbrasil.busca import criar_busca
import re

def extract_citations(texto):
    """Extract citations using simple regex."""
    citacoes = []
    for match in re.finditer(r'\b(?:RESP|REsp|STJ|STF|ARESP)\s+[\d./\s\-]+', texto):
        citacoes.append({
            "inicio": match.start(),
            "fim": match.end(),
            "trecho": match.group(0).strip(),
            "tipo": "jurisprudencia",
            "classificacao": "incompleta",
            "confianca": None,
            "resolucao": None,
        })
    return citacoes

def analyze_file(txt_path, db_path):
    """Analyze confidence calibration on one file."""
    texto = txt_path.read_text(encoding="utf-8")
    busca = criar_busca(db_path=db_path)
    
    citacoes = extract_citations(texto)
    if not citacoes:
        return None
    
    citacoes = busca.aplicar(texto, citacoes)
    
    return {
        "file": txt_path.name,
        "citations": citacoes,
        "total": len(citacoes),
    }

def collect_statistics(results):
    """Collect statistics about confidence calibration."""
    stats = {
        "by_type": defaultdict(lambda: defaultdict(list)),
        "by_class": defaultdict(lambda: defaultdict(list)),
        "by_confidence_bucket": defaultdict(list),
        "overall": {
            "total_citations": 0,
            "with_confidence": 0,
            "conf_distribution": [],
        }
    }
    
    for result in results:
        if not result:
            continue
        
        for cit in result["citations"]:
            classe = cit.get("classificacao")
            tipo = cit.get("tipo")
            conf = cit.get("confianca")
            
            if conf is None:
                continue
            
            # Track by type and class
            stats["by_type"][tipo][classe].append(conf)
            stats["by_class"][classe][tipo].append(conf)
            
            # Track by bucket
            if conf >= 0.9:
                bucket = "very_high"
            elif conf >= 0.75:
                bucket = "high"
            elif conf >= 0.5:
                bucket = "medium"
            elif conf >= 0.25:
                bucket = "low"
            else:
                bucket = "very_low"
            
            stats["by_confidence_bucket"][bucket].append({
                "tipo": tipo,
                "classe": classe,
                "conf": conf
            })
            
            stats["overall"]["total_citations"] += 1
            stats["overall"]["conf_distribution"].append(conf)
    
    stats["overall"]["with_confidence"] = stats["overall"]["total_citations"]
    
    return stats

def print_analysis(stats):
    """Print analysis of confidence calibration."""
    print("\n" + "=" * 70)
    print("PHASE 4: CONFIDENCE CALIBRATION ANALYSIS")
    print("=" * 70)
    
    print(f"\nTotal citations analyzed: {stats['overall']['total_citations']}")
    
    # By type and class
    print("\n--- BY TYPE & CLASS ---")
    for tipo in sorted(stats["by_type"].keys()):
        print(f"\n{tipo.upper()}:")
        for classe in sorted(stats["by_type"][tipo].keys()):
            confs = stats["by_type"][tipo][classe]
            if confs:
                avg = sum(confs) / len(confs)
                print(f"  {classe:12} - avg={avg:.3f}, min={min(confs):.3f}, max={max(confs):.3f}, n={len(confs)}")
    
    # By confidence bucket
    print("\n--- BY CONFIDENCE BUCKET ---")
    buckets = ["very_high", "high", "medium", "low", "very_low"]
    for bucket in buckets:
        items = stats["by_confidence_bucket"][bucket]
        if items:
            print(f"\n{bucket.upper()} (n={len(items)}):")
            # Count by class
            by_class = defaultdict(int)
            for item in items:
                by_class[item["classe"]] += 1
            for classe in sorted(by_class.keys()):
                print(f"  {classe}: {by_class[classe]}")
    
    # Overall distribution
    if stats["overall"]["conf_distribution"]:
        confs = stats["overall"]["conf_distribution"]
        print(f"\nOverall confidence distribution:")
        print(f"  Mean: {sum(confs)/len(confs):.3f}")
        print(f"  Min: {min(confs):.3f}")
        print(f"  Max: {max(confs):.3f}")
        print(f"  Median: {sorted(confs)[len(confs)//2]:.3f}")

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("Phase 4: Collecting calibration data...")
    print("=" * 70)
    
    txt_dir = Path("data/txt")
    db_path = Path("data/desafio1_bracis.db")
    
    if not db_path.exists() or not txt_dir.exists():
        print("ERROR: Missing data files")
        sys.exit(1)
    
    # Process first 20 files
    txt_files = sorted(txt_dir.glob("*.txt"))[:20]
    results = []
    
    print(f"\nProcessing {len(txt_files)} files...")
    for i, txt_file in enumerate(txt_files, 1):
        try:
            result = analyze_file(txt_file, db_path)
            if result:
                results.append(result)
                print(f"  [{i}/{len(txt_files)}] {txt_file.name}: {result['total']} citations")
        except Exception as e:
            print(f"  [{i}/{len(txt_files)}] {txt_file.name}: ERROR - {e}")
    
    # Analyze
    stats = collect_statistics(results)
    print_analysis(stats)
    
    print("\n" + "=" * 70)
    print("Analysis complete. Use these stats to optimize Phase 4:")
    print("  - Adjust base confidence values if averages are too high/low")
    print("  - Add tribunal-specific calibration if patterns emerge")
    print("  - Test new multiplier strategies")
    print("=" * 70 + "\n")

