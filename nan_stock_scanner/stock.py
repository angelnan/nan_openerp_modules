# -*- encoding: utf-8 -*-
##############################################################################
#
# Copyright (c) 2009-2012 NaN Projectes de Programari Lliure, S.L.
#                         All Rights Reserved.
#                         http://www.NaN-tic.com
#
# WARNING: This program as such is intended to be used by professional
# programmers who take the whole responsability of assessing all potential
# consequences resulting from its eventual inadequacies and bugs
# End users who are looking for a ready-to-use solution with commercial
# garantees and support are strongly adviced to contract a Free Software
# Service Company
#
# This program is Free Software; you can redistribute it and/or
# modify it under the terms of the GNU Affero General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA  02111-1307, USA.
#
##############################################################################

from osv import fields,osv
from tools.translate import _
import decimal_precision as dp


class res_company(osv.osv):
    _inherit = 'res.company'

    _columns = {
        'scanner_lot_creation': fields.selection([('none','None'),('search-create','Search reference & create'),('always','Always')], 'Lot Creation', required=False, readonly=False, help='If set to "Search reference & create" the system will search the reference introduced in the lot and will create one if it''s not found. If set to "Always" it will create a lot even if one with the same number exists.'),
        'scanner_fill_quantity': fields.boolean('Fill Quantity', help='Mark pending quantity must be loaded when product is scanned' ),
    }

res_company()

 
class stock_picking(osv.osv):
    _inherit = 'stock.picking'

    def onchange_scanned_ean(self, cr, uid, ids, product_id, ean13, context):
        if not ids or not (product_id and ean13) :
            return {
                'value': {},
                'warning': {
                    'title': _('EAN13 code update'), 
                    'message': _('Please select product First')
                } 
            }
        product = self.pool.get('product.product').browse(cr,uid, product_id , context=context )

        if ean13 and len(ean13) ==  13:
            return {
                'value':{},
                'warning': {
                    'title': _('EAN13 code update'),
                    'message': _('Number %(number)s will be updated to product %(product)s\nCurrent EAN13: %(current)s') % {
                        'number': ean13,
                        'product': product.name or '',
                        'current': product.ean13 or '',
                    } 
                } 
            }
        elif ean13 and len(ean13) != 13:
            return {
                'value': {},
                'warning': {
                    'title': _('EAN13 code update'),
                    'message': _('Number %s invalid') % ean13 
                } 
            }
        return {}

    def on_change_scanned_product(self, cr, uid, ids, product_id, scanned_quantity, context):

        if not ids or not product_id:
            return {}

        picking = self.browse(cr, uid, ids[0], context)

        company = self.pool.get('res.users').browse(cr, uid, uid, context).company_id

        result={'value':{}}
        for move in picking.pending_move_line_ids:
            if move.product_id.id == product_id:
                if len(move.product_id.packaging) == 1:
                    result['value']['scanned_packaging_id'] = move.product_id.packaging[0].id
                if company.scanner_fill_quantity:
                    result['value']['scanned_quantity'] = move.pending_quantity
                elif scanned_quantity == 0:
                    result['value']['scanned_quantity'] = 1

                if move.purchase_line_id:
                    result['value']['scanned_price_unit'] = move.purchase_line_id.price_unit
                else:
                    result['value']['scanned_price_unit'] = move.product_id.standard_price

                return result
        return { 
            'warning': {
                'title': _('Product Error'),
                'message': _('This product is not pending to be scanned in this order.'),
            }
        }

    def _pending_move_line_ids(self, cr, uid, ids, field_name, arg, context=None):
        result = {}
        for picking in self.browse(cr, uid, ids, context):
            lines = []
            for line in picking.move_lines:
                if line.product_qty - line.received_quantity > 0:
                    lines.append( line.id )
            result[picking.id] = lines
        return result

    def _in_matching_moves(self, move_lines, scanned_product_id, scanned_lot_ref):
        """Get possible scanned move"""
        moves =  []
        for move in move_lines:
            if move.product_id.id == scanned_product_id:
                if move.prodlot_id and move.prodlot_id.ref == scanned_lot_ref:
                    moves.insert( 0, move )
                    continue
                moves.append( move )
        return moves

    def _out_matching_moves(self, move_lines, scanned_product_id, scanned_lot_id):
        """Get possible scanned move"""
        moves =  []
        
        for move in move_lines:
            if move.product_id.id == scanned_product_id:
                if scanned_lot_id and move.prodlot_id:
                    if scanned_lot_id == move.prodlot_id.id:
                        moves.insert( 0, move )
                        continue
                else:
                    moves.append( move )
        return moves

    def _scanned_product(self, cr, uid, ids, context):        
        move_ids = []

        lot_creation = self.pool.get('res.users').browse(cr, uid, uid, context).company_id.scanner_lot_creation

        for picking in self.browse(cr, uid, ids, context):
            if not picking.scanned_product_id:
                continue
            if picking.scanned_quantity <= 0:
                continue
            scanned_product_id = picking.scanned_product_id.id
            pending_quantity = picking.scanned_quantity
            scanned_lot_ref = picking.scanned_lot_ref
            scanned_lot_id = picking.scanned_lot_id and picking.scanned_lot_id.id or False
            packing_id =  picking.scanned_packaging_id and picking.scanned_packing_id.id
            scanned_use_date = picking.scanned_use_date
            scanned_price_unit = picking.scanned_price_unit

            if picking.type == 'in':
                moves = self._in_matching_moves(picking.move_lines, scanned_product_id, scanned_lot_ref)
                for move in moves:
                    if pending_quantity <= 0:
                        break
                    qty = min(pending_quantity, move.pending_quantity)
                    if qty == 0:
                        continue

                    lot_id = False
                    create_lot = False
                    if lot_creation == 'search-create' and scanned_lot_ref:
                        lot_ids = self.pool.get('stock.production.lot').search(cr, uid, [('ref','=',scanned_lot_ref)], context=context)
                        if lot_ids:
                            lot_id = lot_ids[0]
                        else:
                            create_lot = True

                    if lot_creation == 'always' or create_lot:
                        lot_id = self.pool.get('stock.production.lot').create(cr, uid, {
                            'ref': scanned_lot_ref,
                            'product_id': scanned_product_id,
                            'use_date': scanned_use_date,
                        }, context)

                    move_prodlot_id = move.prodlot_id and move.prodlot_id.id or False
                    if move_prodlot_id == lot_id:
                        self.pool.get('stock.move').write(cr, uid, [move.id], {
                            'prodlot_id': lot_id,
                            'received_quantity': move.received_quantity + qty,
                            'product_packaging': packing_id,
                            'scanned_price_unit' : scanned_price_unit,
                        }, context)
                    else:
                        # If move.prodlot_id != lot_id it means that move.prodlot_id == False
                        self.pool.get('stock.move').write(cr, uid, [move.id], {
                            'prodlot_id': lot_id,
                            'product_qty': qty,
                            'product_uos_qty': qty,
                            'received_quantity': qty,
                            'product_packaging': packing_id,
                            'scanned_price_unit' : scanned_price_unit,
                        }, context)

                        if move.product_qty - qty > 0:
                            move_copy_id = self.pool.get('stock.move').copy(cr, uid, move.id, {
                                'product_qty' : move.product_qty - qty,
                                'product_uos_qty': move.product_qty - qty,
                                'received_quantity': move.received_quantity, 
                                'state': move.state,
                                'prodlot_id': None,
                            }, context)

                    move_ids.append( move.id )
                    pending_quantity -= qty

                if pending_quantity:
                    if pending_quantity == picking.scanned_quantity:
                        raise osv.except_osv(_('Product Error'), _('There are no pending moves with this product.'))
                    else:
                        raise osv.except_osv(_('Product Error'),
                            _('Wrong product quantity. Expected %(expected).2f at most but you introduced %(introduced).2f.') % {
                                'expected': picking.scanned_quantity - pending_quantity,
                                'introduced': picking.scanned_quantity,
                            })

            else:
                moves = self._out_matching_moves(picking.move_lines, scanned_product_id, scanned_lot_id)
                for move in moves:
                    qty = min(pending_quantity, move.pending_quantity)
                    if qty == 0:
                        continue
                    create_lot = True

                    lot_id = scanned_lot_id or move.prodlot_id and move.prodlot_id.id or False
                    move_prodlot_id = move.prodlot_id and move.prodlot_id.id or False

                    if move_prodlot_id == lot_id:
                        self.pool.get('stock.move').write(cr, uid, [move.id], {
                            'prodlot_id': lot_id,
                            'received_quantity': move.received_quantity + qty,
                            'product_packaging': packing_id,
                        }, context)
                    else:
                        self.pool.get('stock.move').write(cr, uid, [move.id], {
                            'product_qty': qty,
                            'product_uos_qty': qty,
                            'received_quantity': qty,
                            'prodlot_id': lot_id,
                            'product_packaging': packing_id,
                        }, context)
                        if move.product_qty - qty > 0:
                            move_copy_id = self.pool.get('stock.move').copy(cr, uid, move.id, {
                                'product_qty' : move.product_qty - qty,
                                'product_uos_qty': move.product_qty - qty,
                                'received_quantity': move.received_quantity, 
                                'state': move.state,
                                'prodlot_id': None,
                            })

                    move_ids.append( move.id )
                    pending_quantity -= qty
                    if pending_quantity <= 0:
                        break

                if pending_quantity:
                    if pending_quantity == picking.scanned_quantity:
                        raise osv.except_osv(_('Product Error'), _('There are no pending moves with this product.'))
                    else:
                        raise osv.except_osv(_('Product Error'),
                            _('Wrong product quantity. Expected %(expected).2f at most but you introduced %(introduced).2f.') % {
                                'expected': picking.scanned_quantity - pending_quantity,
                                'introduced': picking.scanned_quantity,
                            })

        self.pool.get('stock.picking').write(cr, uid, ids, {
            'scanned_product_id': False,
            'scanned_quantity': 0,
            'scanned_lot_ref': False,
            'scanned_lot_id': False,
            'scanned_packaging_id': False,
            'scanned_use_date': False,
            'scanned_ean':False,
            'scanned_price_unit': False,
        }, context)
        return move_ids

    def action_scanned(self, cr, uid, ids, context=None):
        pick = self.browse( cr, uid, ids , context=context)[0]

        scanned_product = pick.scanned_product_id.id
        scanned_ean = pick.scanned_ean
        if pick.scanned_product_id or pick.scanned_quantity:
           # Call _scanned_product if either one of the two fields are updated because
           # the function will reset their values to NULL
           self._scanned_product(cr, uid, ids, context)

        if scanned_ean and len(scanned_ean) ==  13:
            self.pool.get('product.product').write( cr, uid,scanned_product, {'ean13':scanned_ean} ,context=context)


        return False

    def action_reset(self, cr, uid, ids, context=None):
        pick = self.browse( cr, uid, ids , context=context)[0]

        for line in pick.pending_move_line_ids:
            if line.state == 'assigned':
                quantity = line.product_qty
            else:
                quantity = 0.0
            self.pool.get('stock.move').write(cr, uid, [line.id], {
                'received_quantity': quantity,
            }, context=context)
        return False

    _columns = {
        'pending_move_line_ids': fields.function(_pending_move_line_ids, method=True, type='one2many', relation='stock.move', string='Pending Lines', store=False, help='List of pending products to be received.'),
        'scanned_product_id': fields.many2one('product.product', 'Scanned product', states={'assigned': [('readonly', False)], 'confirmed':[('readonly',False)]}, readonly=True, help='Scan the code of the next product.'),
        'scanned_quantity': fields.float('Quantity', states={'assigned': [('readonly', False)],'confirmed':[('readonly',False)]}, readonly=True, digits_compute=dp.get_precision('Product UoM'),help='Quantity of the scanned product.'),
        'scanned_lot_ref': fields.char('Supplier Lot Ref.', size=64, states={'assigned': [('readonly', False)]}, readonly=True, help="Supplier's lot reference."),
        'scanned_packaging_id': fields.many2one('product.packaging', 'Packaging', states={'assigned': [('readonly', False)]}, readonly=True, help="Product's packaging."),
        'scanned_price_unit': fields.float('Unit Price', digits_compute= dp.get_precision('Cost Price')),
        'scanned_use_date': fields.date('DLUO', states={'assigned': [('readonly', False)]}, readonly=True, help="Lot's expire date."),
        'scanned_ean': fields.char('Ean13',size=13,help='Type ean for update on  current product'),
        'scanned_lot_id': fields.many2one('stock.production.lot', 'Stock Production Lot'),
    }

    def action_force_scanner_confirm(self, cr, uid, ids, context=None):
        for picking in self.browse(cr, uid, ids, context):
            for move in picking.move_lines:
                self.pool.get('stock.move').write( cr, uid, [move.id], {
                    'received_quantity': move.product_qty,
                }, context=context) 
        return self.action_scanner_confirm( cr, uid, ids, context )

    def action_scanner_confirm(self, cr, uid, ids, context=None):
        data = {}
        total_received = 0
        for picking in self.browse(cr, uid, ids, context):
            for move in picking.move_lines:
                total_received += move.received_quantity
                item = {}
                item['product_qty'] = move.received_quantity
                item['received_quantity'] = 0
                item['product_uom'] = move.product_uom.id
                item['product_price'] = move.scanned_price_unit
                item['product_currency'] = self.pool.get('res.users').browse(cr, uid, uid, context).company_id.currency_id.id
                item['prodlot_id'] = move.prodlot_id and move.prodlot_id.id
                data['move%s' % move.id] = item

        if not total_received:
            return {}

        res = self.do_partial(cr, uid, ids, data, context)
        move_ids = []
        for picking in self.browse(cr, uid, ids, context):
            if  res.get(picking.id) and res[picking.id]['delivered_picking'] != picking.id:
                move_ids += [x.id for x in picking.move_lines]

        self.pool.get('stock.move').write(cr, uid, move_ids, {
            'received_quantity': 0,
        }, context)

        return res

stock_picking()


class stock_move(osv.osv):
    _inherit = 'stock.move'
    
    # stock.move
    def _pending_quantity(self, cr, uid, ids, field_name, arg, context=None):
        result = {}
        for move in self.browse(cr, uid, ids, context):
            result[move.id] = move.product_qty - move.received_quantity
        return result
    
    # stock.move
    def create(self, cr, uid, vals, context=None):
        if vals.get('purchase_line_id') and 'scanned_price_unit' not in vals:
            purchase_line = self.pool.get('purchase.order.line').browse(cr, uid,
                    vals['purchase_line_id'], context)
            vals['scanned_price_unit'] = purchase_line.price_unit
        
        return super(stock_move, self).create(cr, uid, vals, context)
    
    # stock.move
    def write(self, cr, uid, ids, values, context=None):
        if 'scanned_price_unit' in values:
            line_ids = []
            for move in self.browse(cr, uid, ids, context):
                if move.purchase_line_id:
                    line_ids.append( move.purchase_line_id.id )

            if line_ids:
                self.pool.get('purchase.order.line').write(cr, uid, line_ids, {
                    'price_unit': values['scanned_price_unit'],
                }, context)
        return super(stock_move, self).write(cr, uid, ids, values, context)

    _columns = {
        'received_quantity': fields.float('Received Quantity',digits_compute=dp.get_precision('Product UoM'),  help='Quantity of product received'),
        'pending_quantity': fields.function(_pending_quantity, digits_compute=dp.get_precision('Product UoM'), method=True, type='float', string='Pending Quantity', store=False, help='Quantity pending to be received'),
        'scanned_price_unit': fields.float('Scanned Price Unit', digits_compute=dp.get_precision('Sale Price')),
    }

stock_move()


class product_product(osv.osv):
    _inherit = 'product.product'

    def name_search(self, cr, user, name='', args=None, operator='ilike', context=None, limit=80):
        result = super(product_product,self).name_search(cr, user, name, args, operator, context, limit)
        if name and not result:
            info_ids = self.pool.get('product.supplierinfo').search(cr, user, [('product_barcode',operator,name)], context=context, limit=limit)
            ids = []
            for info in self.pool.get('product.supplierinfo').browse(cr, user, info_ids, context):
                ids.append( info.product_id.id )
            result += self.name_get(cr, user, ids, context)
        return result
product_product()

class product_supplierinfo(osv.osv):
    _inherit = 'product.supplierinfo'
    _columns = {
        'product_barcode': fields.char('Product Barcode', size=30, help='The barcode for this product of this supplier.'),
    }
product_supplierinfo()

class nan_stock_picking_scanner_confirm_wizard(osv.osv_memory):
    _name = 'nan.stock.picking.scanner.confirm.wizard'

    def action_force_scanner_confirm( self, cr, uid, ids, context=None):
        return self.pool.get('stock.picking').action_force_scanner_confirm( cr, uid, [context['active_id']],context)

    def action_scanner_confirm(self, cr, uid, ids, context=None):
        return self.pool.get('stock.picking').action_scanner_confirm(cr, uid, [context['active_id']], context)
nan_stock_picking_scanner_confirm_wizard()

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:

