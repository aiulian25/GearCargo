// @vitest-environment node
import { describe, it } from 'vitest'
import { RuleTester } from 'eslint'
import accessibleNames from '../../eslint-rules/accessibleNames.js'

RuleTester.describe = describe
RuleTester.it = it

const ruleTester = new RuleTester({
  languageOptions: { ecmaVersion: 'latest', sourceType: 'module', parserOptions: { ecmaFeatures: { jsx: true } } },
})
const reported = messageId => code => ({ code, errors: [{ messageId }] })

ruleTester.run('control-has-name', accessibleNames.rules['control-has-name'], {
  valid: [
    "<button>{t('common.save')}</button>",
    "<button aria-label={t('common.close')}>{Icons.close}</button>",
    "<button title={t('common.edit')}>{Icons.edit}</button>",
    "<button>{Icons.plus}<span>{t('admin.addUser')}</span></button>",
    '<button>{tab.label}</button>',
    "<button><span className='sr-only'>{t('common.close')}</span>{Icons.close}</button>",
    "<Link to='/x'>{Icons.plus}{t('consumables.add')}</Link>",
    '<button><img src={avatar} alt={user.name} /></button>',
    '<button {...props} />',
    "<button aria-label={t('common.close')}><span aria-hidden='true' className='material-icons-outlined'>close</span></button>",
    // The hidden ligature leaves the title as the name.
    "<button title={t('reminders.markComplete')}><span aria-hidden='true' className='material-icons-outlined'>check</span></button>",
  ],
  invalid: [
    ...[
      '<button onClick={close}>{Icons.close}</button>',
      "<button><svg viewBox='0 0 24 24'><path d='M0 0' /></svg></button>",
      "<button><TrashIcon className='w-4 h-4' /></button>",
      '<button>{open ? Icons.chevronUp : Icons.chevronDown}</button>',
      "<button>{Icons.plus}<span className='hidden sm:inline'>{t('admin.addUser')}</span></button>",
      "<Link to='/add'>{Icons.plus}</Link>",
      // A whitespace literal is not text.
      "<button>{Icons.close}{' '}</button>",
    ].map(reported('iconOnly')),
    ...[
      "<button><span className='material-icons-outlined'>close</span></button>",
      "<button title={t('common.edit')}><span className='material-icons-outlined'>edit</span></button>",
    ].map(reported('ligatureName')),
  ],
})

ruleTester.run('field-has-label', accessibleNames.rules['field-has-label'], {
  valid: [
    "<><label htmlFor='date'>{t('addFuel.date')}</label><input id='date' type='date' /></>",
    "<><input id='odometer' /><label htmlFor='odometer'>{t('addFuel.mileage')}</label></>",
    "<label>{t('backup.enabled')}<input type='checkbox' /></label>",
    "<input aria-label={t('common.search')} />",
    "<input type='hidden' name='token' />",
    "<input type='file' className='hidden' />",
    "<FormField id='visit-notes' label={t('appointments.notes')}><textarea id='visit-notes' /></FormField>",
    '<>{keys.map(key => <div key={key}><label htmlFor={`ai-model-${key}`}>{key}</label><select id={`ai-model-${key}`} /></div>)}</>',
    // A useId() value shared by the label and the field.
    "<><label htmlFor={id}>{t('settings.currency')}</label><select id={id} /></>",
    "<input type='submit' />",
    "<input type='image' src='/search.png' alt={t('common.search')} />",
  ],
  invalid: [
    "<><label>{t('addFuel.date')}</label><input type='date' /></>",
    // The id is never referenced by a label.
    "<><label>{t('addFuel.date')}</label><input id='date' /></>",
    // The wrapping label has no text.
    "<label className='relative'><input type='checkbox' className='sr-only peer' /><div /></label>",
    '<select value={vehicle} />',
    // A placeholder is not a label.
    "<input placeholder={t('search.placeholder')} />",
    '<label>{Icons.check}<input type="checkbox" /></label>',
    // Option text does not label the field.
    "<label><select><option>{t('common.vehicle')}</option></select></label>",
  ].map(reported('unlabelled')),
})
