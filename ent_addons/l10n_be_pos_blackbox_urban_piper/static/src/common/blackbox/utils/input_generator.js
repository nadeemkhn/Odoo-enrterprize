import { InputGenerator } from "@l10n_be_pos_blackbox/common/blackbox/utils/input_generator";
import { patch } from "@web/core/utils/patch";

patch(InputGenerator.prototype, {
    getCostCenterType(customer, table, order) {
        if (order.delivery_provider_id) {
            return "PLATFORM";
        }
        return super.getCostCenterType(...arguments);
    },
});
