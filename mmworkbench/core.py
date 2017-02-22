# -*- coding: utf-8 -*-
"""This module contains a collection of the core data structures used in workbench."""

from __future__ import unicode_literals
from builtins import object

TEXT_FORM_RAW = 0
TEXT_FORM_PROCESSED = 1
TEXT_FORM_NORMALIZED = 2
TEXT_FORMS = [TEXT_FORM_RAW, TEXT_FORM_PROCESSED, TEXT_FORM_NORMALIZED]


class PlaceholderPreprocessor(object):

    def process(self, text):
        return text

    def generate_character_index_mappings(self, raw, processed):
        return None, None


class QueryFactory(object):
    """An object which encapsulates the components required to create a Query object.

    Attributes:
        preprocessor (Preprocessor): the object responsible for processing raw text
        tokenizer (Tokenizer): the object responsible for normalizing and tokenizing processed
            text
    """
    def __init__(self, sys_ent_rec, tokenizer, preprocessor=None):
        self.tokenizer = tokenizer
        self.preprocessor = preprocessor or PlaceholderPreprocessor()
        self.sys_ent_rec = sys_ent_rec

    def create_query(self, text):
        raw_text = text

        char_maps = {}

        # create raw, processed maps
        processed_text = self.preprocessor.process(raw_text)
        maps = self.preprocessor.generate_character_index_mappings(raw_text, processed_text)
        forward, backward = maps
        char_maps[(TEXT_FORM_RAW, TEXT_FORM_PROCESSED)] = forward
        char_maps[(TEXT_FORM_PROCESSED, TEXT_FORM_RAW)] = backward

        normalized_tokens = self.tokenizer.tokenize(processed_text, False)
        normalized_text = ' '.join([t['entity'] for t in normalized_tokens])

        # create normalized maps
        maps = self.tokenizer.generate_character_index_mappings(processed_text, normalized_text)
        forward, backward = maps

        char_maps[(TEXT_FORM_PROCESSED, TEXT_FORM_NORMALIZED)] = forward
        char_maps[(TEXT_FORM_NORMALIZED, TEXT_FORM_PROCESSED)] = backward

        query = Query(raw_text, processed_text, normalized_tokens, char_maps)
        query.system_entities = self.sys_ent_rec.predict(query)

        return query

    def normalize(self, text):
        return self.tokenizer.normalize(text)

    def __repr__(self):
        return "<QueryFactory id: {!r}>".format(id(self))


class Query(object):
    """The query object is responsible for processing and normalizing raw user text input so that
    classifiers can deal with it. A query stores three forms of text: raw text, processed text, and
    normalized text. The query object is also responsible for translating text ranges across these
    forms.

    Attributes:
        normalized_tokens (list of str): a list of normalized tokens
        raw_text (str): the original input text
        normalized_text (str): the normalized text. TODO: better description here
        processed_text (str): the text after it has been preprocessed. TODO: better description here
    """
    def __init__(self, raw_text, processed_text, normalized_tokens, char_maps):
        """Summary

        Args:
            raw_text (str): the original input text
            processed_text (str): Description
            normalized_tokens (list of dict): List tokens outputted by a tokenizer
            char_maps (dict): Mappings between raw, processed and normalized text
        """
        self._normalized_tokens = normalized_tokens
        self._text = {
            TEXT_FORM_RAW: raw_text,
            TEXT_FORM_PROCESSED: processed_text,
            TEXT_FORM_NORMALIZED: ' '.join([t['entity'] for t in self._normalized_tokens])
        }
        self._char_maps = char_maps
        self.system_entities = None

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        return NotImplemented

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return "<Query {}>".format(self.raw_text.__repr__())

    @property
    def raw_text(self):
        return self._text[TEXT_FORM_RAW]

    @property
    def processed_text(self):
        return self._text[TEXT_FORM_PROCESSED]

    @property
    def normalized_text(self):
        return self._text[TEXT_FORM_NORMALIZED]

    @property
    def normalized_tokens(self):
        return [token['entity'] for token in self._normalized_tokens]

    def transform_range(self, text_range, form_in, form_out):
        """Transforms a text range from one form to another.

        Args:
            text_range (tuple): the range being transformed
            form_in (int): the input text form. Should be one of TEXT_FORM_RAW, TEXT_FORM_PROCESSED
                or TEXT_FORM_NORMALIZED
            form_out (int): the output text form. Should be one of TEXT_FORM_RAW,
                TEXT_FORM_PROCESSED or TEXT_FORM_NORMALIZED

        Returns:
            tuple: the equivalent range of text in the output form
        """
        return (self.transform_index(text_range[0], form_in, form_out),
                self.transform_index(text_range[1], form_in, form_out))

    def transform_index(self, index, form_in, form_out):
        """Transforms a text index from one form to another.

        Args:
            index (int): the index being transformed
            form_in (int): the input form. should be one of TEXT_FORM_RAW
            form_out (int): the output form

        Returns:
            int: the equivalent index of text in the output form
        """
        if form_in not in TEXT_FORMS or form_out not in TEXT_FORMS:
            raise ValueError('Invalid text form')

        if form_in > form_out:
            while form_in > form_out:
                index = self._unprocess_index(index, form_in)
                form_in -= 1
        else:
            while form_in < form_out:
                index = self._process_index(index, form_in)
                form_in += 1
        return index

    def _process_index(self, index, form_in):
        if form_in == TEXT_FORM_NORMALIZED:
            raise ValueError("'{}' form cannot be processed".format(TEXT_FORM_NORMALIZED))
        mapping_key = (form_in, (form_in + 1))
        try:
            mapping = self._char_maps[mapping_key]
        except KeyError:
            # mapping doesn't exist -> use identity
            return index
        # None for mapping means 1-1 mapping
        try:
            return mapping[index] if mapping else index
        except KeyError:
            raise ValueError('Invalid index')

    def _unprocess_index(self, index, form_in):
        if form_in == TEXT_FORM_RAW:
            raise ValueError("'{}' form cannot be unprocessed".form(TEXT_FORM_RAW))
        mapping_key = (form_in, (form_in - 1))
        try:
            mapping = self._char_maps[mapping_key]
        except KeyError:
            # mapping doesn't exist -> use identity
            return index
        # None for mapping means 1-1 mapping
        try:
            return mapping[index] if mapping else index
        except KeyError:
            raise ValueError('Invalid index')


class ProcessedQuery(object):
    """A processed query contains a query and the additional metadata that has been labeled or
    predicted.


    Attributes:
        domain (str): The domain of the query
        entities (list): A list of entities present in this query
        intent (str): The intent of the query
        is_gold (bool): Indicates whether the details in this query were predicted or human labeled
        query (Query): The underlying query object.
    """
    def __init__(self, query, domain=None, intent=None, entities=None, is_gold=False):
        self.query = query
        self.domain = domain
        self.intent = intent
        self.entities = entities
        self.is_gold = is_gold

    def to_dict(self):
        return {
            'query_text': self.query.raw_text,
            'domain': self.domain,
            'intent': self.intent,
            'entities': [e.to_dict() for e in self.entities],
        }

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        return NotImplemented

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        msg = "<ProcessedQuery {}, domain: {}, intent: {}, {} entities{}>"
        return msg.format(self.query.raw_text.__repr__(),  self.domain.__repr__(),
                          self.intent.__repr__(), len(self.entities),
                          ', gold' if self.is_gold else '')


class QueryEntity(object):
    """An entity with the context of the query it came from.

    TODO: account for numeric entities

    Attributes:
        source_raw_text (str): The raw text that was processed into this entity
        source_processed_text (str): The processed text that was processed into this entity
        source_normalized_text (str): The normalized text that was processed into this entity
        start (int): The character index start of the text range that was processed into this
            entity. This index is based on the normalized text of the query passed in.
        end (int): The character index end of the text range that was processed into this
            entity. This index is based on the normalized text of the query passed in.
    """

    def __init__(self, raw_text, processed_text, normalized_text, start, end, entity_type,
                 role=None, value=None, display_text=None, confidence=None):
        """Initializes a query entity object

        Args:
            raw_text (str): Description
            processed_text (str): Description
            normalized_text (str): Description
            start (int): The character index start of the text range that was parsed into this
                entity. This index is based on the raw text of the query passed in.
            end (int): The character index end of the text range that was parsed into this
                entity. This index is based on the raw text of the query passed in.
        """
        self.entity = Entity(entity_type, role, value, display_text or raw_text, confidence)
        self.raw_text = raw_text
        self.processed_text = processed_text
        self.normalized_text = normalized_text
        self.start = start
        self.end = end

    def to_dict(self):
        base = self.entity.to_dict()
        base.update({
            'text': self.raw_text,
            'start': self.start,
            'end': self.end
        })
        return base

    @staticmethod
    def from_query(query, entity_type, start, end, role=None, value=None,
                   display_text=None, confidence=None):
        raw_text = query.raw_text[start:end + 1]

        pro_text_range = query.transform_range((start, end), TEXT_FORM_RAW, TEXT_FORM_PROCESSED)
        processed_text = query.processed_text[pro_text_range[0]:pro_text_range[1] + 1]

        norm_range = query.transform_range((start, end), TEXT_FORM_RAW, TEXT_FORM_NORMALIZED)
        normalized_text = query.normalized_text[norm_range[0]:norm_range[1] + 1]
        return QueryEntity(raw_text, processed_text, normalized_text, start, end,
                           entity_type, role, value, display_text, confidence)

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        return NotImplemented

    def __ne__(self, other):
        return not self.__eq__(other)

    def __str__(self):
        return "{}{}{} '{}' {}-{} ".format(
            self.entity.type, ':' if self.entity.role else '', self.entity.role, self.raw_text,
            self.start, self.end
        )

    def __repr__(self):
        msg = '<QueryEntity {} ({}) [{}-{}]>'
        return msg.format(self.raw_text.__repr__(), self.entity.type.__repr__(),
                          self.start.__repr__(), self.end.__repr__())


class Entity(object):
    """Summary

    Attributes:
        type (str): The type of entity
        role (str): Description
        value (str): The resolved value of the entity
        display_text (str): A human readable text representation of the entity for use in natural
            language responses.
    """
    def __init__(self, entity_type, role, value, display_text, confidence=None):
        self.type = entity_type
        self.role = role
        self.value = value
        self.display_text = display_text
        self.confidence = confidence
        self.system_entity = entity_type.startswith('sys:')

    def to_dict(self):
        base = {
            'type': self.type,
            'role': self.role,
            'value': self.value,
            'display_text': self.display_text
        }
        if self.confidence is not None:
            base['confidence'] = self.confidence

        return base

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        return NotImplemented

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return "<Entity {} ({})>".format(self.display_text.__repr__(), self.type.__repr__())
