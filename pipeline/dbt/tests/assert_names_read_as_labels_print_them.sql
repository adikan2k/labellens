{#
  capitalise() on names that arrive lower-case (macros/text.sql). Returns the rows it gets
  wrong; none means the test passes.
#}
with cases(raw, expected) as (
    values
        ('vitamin e', 'Vitamin E'),
        ('vitamin b12', 'Vitamin B12'),
        ('vitamin d3', 'Vitamin D3'),
        ('vitamins b and c', 'Vitamins B and C'),
        ('dha', 'DHA'),
        ('acesulfame k', 'Acesulfame K'),
        ('Acesulfame k', 'Acesulfame K'),
        ('rebaudioside a', 'Rebaudioside A'),
        ('Patent blue v', 'Patent blue V'),
        ('Green s', 'Green S'),
        ('e150a', 'E150a'),
        ('omega 3 fatty acids', 'Omega 3 fatty acids'),
        ('mono- and diglycerides of fatty acids', 'Mono- and diglycerides of fatty acids'),
        ('salt and a little sugar', 'Salt and a little sugar'),
        ('sea salt', 'Sea salt'),
        ('1‚2-hexanediol', '1,2-hexanediol')
)
select raw, expected, {{ capitalise('raw') }} as got
from cases
where {{ capitalise('raw') }} is distinct from expected
