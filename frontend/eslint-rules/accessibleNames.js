// Local ESLint rules for WCAG 2.1 4.1.2: every button, link and form field
// needs an accessible name that does not come from an icon alone.

const NAMED_CONTROLS = new Set(['button', 'a', 'Link', 'NavLink'])
const FIELD_ELEMENTS = new Set(['input', 'select', 'textarea'])
const LABELLING_COMPONENTS = new Set(['FormField'])
const NAMING_ATTRIBUTES = ['aria-label', 'aria-labelledby']
const FIELD_NAMING_ATTRIBUTES = [...NAMING_ATTRIBUTES, 'title']
// Hidden inputs are never rendered; the other types are named by their value or alt, not by a <label>.
const INPUT_TYPES_WITHOUT_LABEL = new Set(['hidden', 'submit', 'reset', 'button', 'image'])
const FILE_INPUT_TYPE = 'file'
const LIGATURE_CLASS = /\bmaterial-(icons|symbols)/
const HIDDEN_CLASS = /(^|\s)hidden(\s|$)/
const ICON_SET_NAME = /Icons$/
const ICON_VALUE_NAME = /icon$/i
const ICON_COMPONENT_NAME = /Icon$/
const COMPONENT_NAME = /^[A-Z]/

const CONTENT = Object.freeze({ text: 'text', ligature: 'ligature', none: 'none' })
const CONTENT_PRIORITY = [CONTENT.text, CONTENT.ligature, CONTENT.none]
const MESSAGE_BY_CONTENT = { [CONTENT.none]: 'iconOnly', [CONTENT.ligature]: 'ligatureName' }

function elementName(opening) {
  return opening.name.type === 'JSXIdentifier' ? opening.name.name : ''
}

function findAttribute(opening, name) {
  return opening.attributes.find(attribute => attribute.type === 'JSXAttribute' && attribute.name.name === name)
}

function hasAnyAttribute(opening, names) {
  return names.some(name => findAttribute(opening, name))
}

function literalValue(attribute) {
  const value = attribute?.value
  if (value?.type === 'Literal') return value.value
  if (value?.type === 'JSXExpressionContainer' && value.expression.type === 'Literal') return value.expression.value
  return undefined
}

function staticAttributeValue(opening, name) {
  const attribute = findAttribute(opening, name)
  const value = literalValue(attribute)
  if (typeof value === 'string') return value
  const expression = attribute?.value?.expression
  if (expression?.type !== 'TemplateLiteral') return ''
  return expression.quasis.map(quasi => quasi.value.cooked).join(' ')
}

function strongestContent(contents) {
  return CONTENT_PRIORITY.find(content => contents.includes(content)) ?? CONTENT.none
}

function literalContent(value) {
  const isNumber = typeof value === 'number'
  const isVisibleString = typeof value === 'string' && value.trim() !== ''
  return isNumber || isVisibleString ? CONTENT.text : CONTENT.none
}

function isIconReference(expression) {
  if (expression.type === 'Identifier') return ICON_VALUE_NAME.test(expression.name)
  if (expression.type !== 'MemberExpression' || expression.computed) return false
  const isIconSetMember = expression.object.type === 'Identifier' && ICON_SET_NAME.test(expression.object.name)
  return isIconSetMember || ICON_VALUE_NAME.test(expression.property.name)
}

function expressionContent(expression) {
  if (expression.type === 'JSXEmptyExpression') return CONTENT.none
  if (expression.type === 'Literal') return literalContent(expression.value)
  if (expression.type === 'JSXElement') return elementContent(expression)
  if (expression.type === 'JSXFragment') return childrenContent(expression.children)
  if (expression.type === 'ConditionalExpression') {
    return strongestContent([expressionContent(expression.consequent), expressionContent(expression.alternate)])
  }
  if (expression.type === 'LogicalExpression' && expression.operator === '&&') return expressionContent(expression.right)
  if (expression.type === 'LogicalExpression') {
    return strongestContent([expressionContent(expression.left), expressionContent(expression.right)])
  }
  if (isIconReference(expression)) return CONTENT.none
  return CONTENT.text
}

function imageContent(opening) {
  const alt = findAttribute(opening, 'alt')
  if (!alt) return CONTENT.none
  const isEmptyLiteral = alt.value?.type === 'Literal' && alt.value.value.trim() === ''
  return isEmptyLiteral ? CONTENT.none : CONTENT.text
}

function elementContent(element) {
  const opening = element.openingElement
  const name = elementName(opening)
  if (findAttribute(opening, 'aria-hidden')) return CONTENT.none
  // A field's own content, such as <option> text, never names an ancestor control or label.
  if (FIELD_ELEMENTS.has(name)) return CONTENT.none
  if (name === 'img') return imageContent(opening)
  if (name === 'svg' || ICON_COMPONENT_NAME.test(name)) return CONTENT.none
  if (COMPONENT_NAME.test(name)) return CONTENT.text
  const className = staticAttributeValue(opening, 'className')
  if (HIDDEN_CLASS.test(className)) return CONTENT.none
  const content = childrenContent(element.children)
  if (content === CONTENT.text && LIGATURE_CLASS.test(className)) return CONTENT.ligature
  return content
}

function childContent(child) {
  if (child.type === 'JSXText') return child.value.trim() ? CONTENT.text : CONTENT.none
  if (child.type === 'JSXExpressionContainer') return expressionContent(child.expression)
  if (child.type === 'JSXElement') return elementContent(child)
  if (child.type === 'JSXFragment') return childrenContent(child.children)
  return CONTENT.text
}

function childrenContent(children) {
  return strongestContent(children.map(childContent))
}

function isUnlabelledInputType(opening) {
  const type = staticAttributeValue(opening, 'type')
  if (INPUT_TYPES_WITHOUT_LABEL.has(type)) return true
  return type === FILE_INPUT_TYPE && HIDDEN_CLASS.test(staticAttributeValue(opening, 'className'))
}

function hasTextLabelAncestor(opening) {
  for (let node = opening.parent; node; node = node.parent) {
    const isLabel = node.type === 'JSXElement' && elementName(node.openingElement) === 'label'
    if (isLabel) return childrenContent(node.children) === CONTENT.text
  }
  return false
}

const controlHasName = {
  meta: {
    type: 'problem',
    schema: [],
    messages: {
      iconOnly: 'This control shows only icons or hidden text. Give it aria-label={t(...)}, or a title when the content is decorative.',
      ligatureName: 'A Material icon ligature names this control. Add aria-label={t(...)} (or a title) and aria-hidden="true" on the icon span.',
    },
  },
  create(context) {
    return {
      JSXElement(node) {
        const opening = node.openingElement
        if (!NAMED_CONTROLS.has(elementName(opening))) return
        if (hasAnyAttribute(opening, NAMING_ATTRIBUTES)) return
        if (opening.attributes.some(attribute => attribute.type === 'JSXSpreadAttribute')) return
        const content = childrenContent(node.children)
        if (content === CONTENT.text) return
        if (content === CONTENT.none && findAttribute(opening, 'title')) return
        context.report({ node: opening, messageId: MESSAGE_BY_CONTENT[content] })
      },
    }
  },
}

// ponytail: ids are matched by source text within one file, and duplicate ids are not
// detected; resolve real DOM ids (or run axe) if cross-file labels ever appear.
const fieldHasLabel = {
  meta: {
    type: 'problem',
    schema: [],
    messages: {
      unlabelled: 'This field has no accessible name. Point its visible <label htmlFor> at an id, or give it aria-label={t(...)}.',
    },
  },
  create(context) {
    const labelledIds = new Set()
    const unlabelledCandidates = []
    const valueSource = attribute => literalValue(attribute) ?? context.sourceCode.getText(attribute.value.expression)
    const rememberLabelledId = attribute => {
      if (attribute?.value) labelledIds.add(valueSource(attribute))
    }
    const isLabelledById = opening => {
      const id = findAttribute(opening, 'id')
      return Boolean(id?.value) && labelledIds.has(valueSource(id))
    }

    return {
      JSXOpeningElement(opening) {
        const name = elementName(opening)
        if (name === 'label') rememberLabelledId(findAttribute(opening, 'htmlFor'))
        if (LABELLING_COMPONENTS.has(name)) rememberLabelledId(findAttribute(opening, 'id'))
        if (!FIELD_ELEMENTS.has(name)) return
        if (isUnlabelledInputType(opening)) return
        if (hasAnyAttribute(opening, FIELD_NAMING_ATTRIBUTES)) return
        if (hasTextLabelAncestor(opening)) return
        unlabelledCandidates.push(opening)
      },
      'Program:exit'() {
        unlabelledCandidates
          .filter(opening => !isLabelledById(opening))
          .forEach(opening => context.report({ node: opening, messageId: 'unlabelled' }))
      },
    }
  },
}

export default {
  rules: {
    'control-has-name': controlHasName,
    'field-has-label': fieldHasLabel,
  },
}
